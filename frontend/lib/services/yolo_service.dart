import 'dart:convert';
import 'dart:io' show Platform;
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:image/image.dart' as img;
import 'package:onnxruntime/onnxruntime.dart';

/// One detected vegetable, with its box in original-image pixel coordinates.
class Detection {
  final int classId;
  final String label; // canonical id, e.g. "green_beans"
  final double confidence;
  final double x1, y1, x2, y2;

  const Detection(this.classId, this.label, this.confidence, this.x1, this.y1, this.x2, this.y2);

  String get displayName => YoloService.formatClassName(label);

  Map<String, dynamic> toJson() => {
        'class_id': classId,
        'label': label,
        'confidence': double.parse(confidence.toStringAsFixed(4)),
        'box': [x1, y1, x2, y2].map((v) => double.parse(v.toStringAsFixed(1))).toList(),
      };
}

class DetectionResult {
  final List<Detection> detections;
  final int imageWidth;
  final int imageHeight;
  final Duration elapsed;
  const DetectionResult(this.detections, this.imageWidth, this.imageHeight, this.elapsed);
}

/// On-device vegetable detection with the custom YOLO26s model (ONNX).
///
/// Pipeline (mirrors Ultralytics' predictor for a fixed 640x640 export):
///  1. decode + apply EXIF orientation
///  2. letterbox: keep aspect ratio, resize (bilinear), pad with grey 114
///  3. RGB, /255, NCHW float32
///  4. run the model -> [1, 26, 8400] (cx, cy, w, h, 22 class scores)
///  5. confidence filter + class-aware NMS, boxes mapped back to the photo
///
/// Steps 1-3 and 5 run in background isolates; step 4 runs in the
/// onnxruntime plugin's own isolate, so the UI stays responsive.
class YoloService {
  YoloService._();

  static const int inputSize = 640;
  static const double defaultConfidence = 0.25;
  static const double defaultIou = 0.7; // Ultralytics default

  static OrtSession? _session;
  static List<String> _labels = const [];
  static Future<void>? _loading;

  static List<String> get labels => _labels;

  @visibleForTesting
  static set labelsForTest(List<String> v) => _labels = v;

  static String formatClassName(String name) =>
      name.split('_').where((w) => w.isNotEmpty).map((w) => '${w[0].toUpperCase()}${w.substring(1)}').join(' ');

  static bool get isSupported => !kIsWeb;

  /// Loads the model once. Safe to call repeatedly.
  static Future<void> initialize() {
    if (_session != null) return Future.value();
    return _loading ??= _load().whenComplete(() => _loading = null);
  }

  static Future<void> _load() async {
    if (!isSupported) {
      throw UnsupportedError('On-device detection is not available on the web.');
    }
    final meta = jsonDecode(await rootBundle.loadString('assets/models/labels.json')) as Map<String, dynamic>;
    final names = List<String>.from(meta['names'] as List);
    if (names.length != 22) throw StateError('Model metadata lists ${names.length} classes, expected 22.');
    final raw = await rootBundle.load('assets/models/best.onnx');
    OrtEnv.instance.init();
    final options = OrtSessionOptions()..setIntraOpNumThreads(min(4, max(1, _cpuCount())));
    _session = OrtSession.fromBuffer(raw.buffer.asUint8List(raw.offsetInBytes, raw.lengthInBytes), options);
    _labels = names;
  }

  static int _cpuCount() {
    try {
      return Platform.numberOfProcessors;
    } catch (_) {
      return 2;
    }
  }

  static Future<DetectionResult> detect(
    Uint8List imageBytes, {
    double confidence = defaultConfidence,
    double iou = defaultIou,
  }) async {
    final sw = Stopwatch()..start();
    await initialize();
    final prep = await compute(preprocess, imageBytes);

    final input = OrtValueTensor.createTensorWithDataList(prep.tensor, [1, 3, inputSize, inputSize]);
    final runOptions = OrtRunOptions();
    List<OrtValue?>? outputs;
    try {
      outputs = await _session!.runAsync(runOptions, {'images': input});
      if (outputs == null || outputs.isEmpty || outputs.first == null) {
        throw StateError('The model returned no output.');
      }
      final flat = _flatten(outputs.first!.value);
      final dets = await compute(
        decodeOutput,
        DecodeArgs(flat, prep.scale, prep.padX, prep.padY, prep.width, prep.height, confidence, iou, _labels),
      );
      return DetectionResult(dets, prep.width, prep.height, sw.elapsed);
    } finally {
      input.release();
      runOptions.release();
      for (final o in outputs ?? const <OrtValue?>[]) {
        o?.release();
      }
    }
  }

  static Float32List _flatten(dynamic value) {
    // value: [1][26][8400] nested lists
    final rows = (value as List).first as List;
    final channels = rows.length;
    final anchors = (rows.first as List).length;
    final out = Float32List(channels * anchors);
    for (var c = 0; c < channels; c++) {
      final row = rows[c] as List;
      for (var j = 0; j < anchors; j++) {
        out[c * anchors + j] = (row[j] as num).toDouble();
      }
    }
    return out;
  }
}

/// Output of [preprocess].
class Preprocessed {
  final Float32List tensor;
  final double scale;
  final double padX;
  final double padY;
  final int width;
  final int height;
  const Preprocessed(this.tensor, this.scale, this.padX, this.padY, this.width, this.height);
}

/// Decode, orient and letterbox an image into a 1x3x640x640 float tensor.
/// Top-level so it can run in a background isolate.
Preprocessed preprocess(Uint8List bytes) {
  const size = YoloService.inputSize;
  final decoded = img.decodeImage(bytes);
  if (decoded == null) {
    throw const FormatException('This file could not be read as an image.');
  }
  final image = img.bakeOrientation(decoded);
  final w = image.width, h = image.height;

  final r = min(size / w, size / h);
  final newW = (w * r).round(), newH = (h * r).round();
  final dw = (size - newW) / 2, dh = (size - newH) / 2;
  final left = (dw - 0.1).round(), top = (dh - 0.1).round();

  final resized = (newW == w && newH == h)
      ? image
      : img.copyResize(image, width: newW, height: newH, interpolation: img.Interpolation.linear);

  const plane = size * size;
  final tensor = Float32List(3 * plane)..fillRange(0, 3 * plane, 114 / 255.0);
  for (var y = 0; y < newH; y++) {
    final rowOffset = (y + top) * size + left;
    for (var x = 0; x < newW; x++) {
      final p = resized.getPixel(x, y);
      final i = rowOffset + x;
      tensor[i] = p.rNormalized.toDouble();
      tensor[plane + i] = p.gNormalized.toDouble();
      tensor[2 * plane + i] = p.bNormalized.toDouble();
    }
  }
  return Preprocessed(tensor, r, left.toDouble(), top.toDouble(), w, h);
}

class DecodeArgs {
  final Float32List output;
  final double scale, padX, padY;
  final int width, height;
  final double confidence, iou;
  final List<String> labels;
  const DecodeArgs(this.output, this.scale, this.padX, this.padY, this.width, this.height, this.confidence, this.iou,
      this.labels);
}

/// Confidence filtering + class-aware NMS on the raw [1, 4+nc, anchors] head.
List<Detection> decodeOutput(DecodeArgs a) {
  final nc = a.labels.length;
  final anchors = a.output.length ~/ (4 + nc);
  final cands = <Detection>[];
  for (var j = 0; j < anchors; j++) {
    var best = -1.0;
    var cls = -1;
    for (var c = 0; c < nc; c++) {
      final s = a.output[(4 + c) * anchors + j];
      if (s > best) {
        best = s;
        cls = c;
      }
    }
    if (best < a.confidence) continue;
    final cx = a.output[j], cy = a.output[anchors + j];
    final bw = a.output[2 * anchors + j], bh = a.output[3 * anchors + j];
    double mapX(double v) => ((v - a.padX) / a.scale).clamp(0.0, a.width.toDouble());
    double mapY(double v) => ((v - a.padY) / a.scale).clamp(0.0, a.height.toDouble());
    cands.add(Detection(cls, a.labels[cls], best, mapX(cx - bw / 2), mapY(cy - bh / 2), mapX(cx + bw / 2), mapY(cy + bh / 2)));
  }
  cands.sort((x, y) => y.confidence.compareTo(x.confidence));

  final kept = <Detection>[];
  for (final c in cands) {
    var suppressed = false;
    for (final k in kept) {
      if (k.classId == c.classId && _iou(k, c) > a.iou) {
        suppressed = true;
        break;
      }
    }
    if (!suppressed) kept.add(c);
    if (kept.length >= 300) break;
  }
  return kept;
}

double _iou(Detection a, Detection b) {
  final ix = max(0.0, min(a.x2, b.x2) - max(a.x1, b.x1));
  final iy = max(0.0, min(a.y2, b.y2) - max(a.y1, b.y1));
  final inter = ix * iy;
  final union = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - inter;
  return union <= 0 ? 0 : inter / union;
}
