// Runs the app's real on-device detection pipeline (YoloService + ONNX
// Runtime) on a set of images and prints the detections, so they can be
// compared with Ultralytics' predictions for the original best.pt model.
//
//   python3 -m http.server 8765 --directory <images-with-manifest.json>
//   flutter test integration_test/yolo_validation_test.dart -d macos \
//     --dart-define=IMAGE_SERVER=http://127.0.0.1:8765
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:integration_test/integration_test.dart';
import 'package:pantry_pilot_ai/services/yolo_service.dart';

const server = String.fromEnvironment('IMAGE_SERVER');

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('on-device YOLO pipeline produces detections', (tester) async {
    expect(server, isNotEmpty, reason: 'pass --dart-define=IMAGE_SERVER=...');
    await tester.runAsync(() async {
      await YoloService.initialize();
      expect(YoloService.labels, hasLength(22));
      final manifest = jsonDecode((await http.get(Uri.parse('$server/manifest.json'))).body) as List;
      final timings = <int>[];
      for (final entry in manifest) {
        final file = entry['file'] as String;
        final bytes = (await http.get(Uri.parse('$server/$file'))).bodyBytes;
        final r = await YoloService.detect(bytes);
        timings.add(r.elapsed.inMilliseconds);
        // ignore: avoid_print
        print('YOLO_RESULT ${jsonEncode({'file': file, 'detections': r.detections.map((d) => d.toJson()).toList()})}');
      }
      timings.sort();
      // ignore: avoid_print
      print('YOLO_TIMING median_ms=${timings[timings.length ~/ 2]} max_ms=${timings.last}');
    });
  });
}
