import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:pantry_pilot_ai/config/app_config.dart';
import 'package:pantry_pilot_ai/services/yolo_service.dart';
import 'package:pantry_pilot_ai/widgets/ui.dart';

const labels = ['a', 'b', 'c'];

/// Builds a fake [1, 4+nc, anchors] output tensor.
Float32List fakeOutput(List<List<double>> anchors) {
  final n = anchors.length, ch = 4 + labels.length;
  final out = Float32List(ch * n);
  for (var j = 0; j < n; j++) {
    for (var c = 0; c < ch; c++) {
      out[c * n + j] = anchors[j][c];
    }
  }
  return out;
}

void main() {
  group('YOLO decoding', () {
    test('filters by confidence, keeps best class, maps letterbox back to the photo', () {
      // Photo 1280x640 -> scale 0.5, letterboxed into 640x640 with 160 px padding top/bottom.
      final out = fakeOutput([
        [320, 320, 100, 50, 0.1, 0.9, 0.2], // class b, centre of the image
        [100, 100, 20, 20, 0.2, 0.1, 0.1], // below threshold
      ]);
      final dets = decodeOutput(DecodeArgs(out, 0.5, 0, 160, 1280, 640, 0.25, 0.7, labels));
      expect(dets, hasLength(1));
      final d = dets.single;
      expect(d.label, 'b');
      expect(d.confidence, closeTo(0.9, 1e-6));
      expect([d.x1, d.y1, d.x2, d.y2], [540, 270, 740, 370]);
    });

    test('class-aware NMS suppresses overlapping boxes of the same class only', () {
      final out = fakeOutput([
        [100, 100, 50, 50, 0.9, 0, 0],
        [102, 101, 50, 50, 0.8, 0, 0], // same class, IoU ~0.9 -> suppressed
        [102, 101, 50, 50, 0, 0.7, 0], // different class -> kept
        [400, 400, 50, 50, 0.6, 0, 0], // same class, far away -> kept
      ]);
      final dets = decodeOutput(DecodeArgs(out, 1, 0, 0, 640, 640, 0.25, 0.7, labels));
      expect(dets.map((d) => '${d.label}${d.confidence}'), ['a0.8999999761581421', 'b0.699999988079071', 'a0.6000000238418579']);
    });

    test('boxes are clamped to the image', () {
      final out = fakeOutput([
        [5, 5, 40, 40, 0.9, 0, 0],
      ]);
      final d = decodeOutput(DecodeArgs(out, 1, 0, 0, 640, 640, 0.25, 0.7, labels)).single;
      expect(d.x1, 0);
      expect(d.y1, 0);
    });
  });

  test('letterbox preprocessing keeps aspect ratio and pads with grey 114', () {
    final photo = img.Image(width: 200, height: 100);
    img.fill(photo, color: img.ColorRgb8(255, 0, 0));
    final p = preprocess(img.encodePng(photo));
    expect(p.width, 200);
    expect(p.height, 100);
    expect(p.scale, 3.2);
    expect(p.padX, 0);
    expect(p.padY, 160);
    const plane = 640 * 640;
    // Top-left pixel is padding (grey), centre pixel is red.
    expect(p.tensor[0], closeTo(114 / 255, 1e-6));
    const centre = 320 * 640 + 320;
    expect(p.tensor[centre], closeTo(1.0, 1e-6));
    expect(p.tensor[plane + centre], closeTo(0.0, 1e-6));
  });

  test('preprocess rejects non-images', () {
    expect(() => preprocess(Uint8List.fromList([1, 2, 3])), throwsFormatException);
  });

  group('AppConfig', () {
    test('normalises base URLs', () {
      expect(AppConfig.normalize('https://x.onrender.com'), 'https://x.onrender.com/api');
      expect(AppConfig.normalize('https://x.onrender.com/api/'), 'https://x.onrender.com/api');
    });
    test('rejects malformed URLs', () {
      expect(AppConfig.validate('not a url'), isNotNull);
      expect(AppConfig.validate('ftp://x.com'), isNotNull);
      expect(AppConfig.validate('https://x.onrender.com'), isNull);
    });
  });

  test('money formatting uses Indian digit grouping', () {
    expect(formatMoney(0), '₹0');
    expect(formatMoney(1234567), '₹12,34,567');
    expect(formatMoney(999.5), '₹999.50');
  });
}
