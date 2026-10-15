import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../../services/yolo_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/ui.dart';
import 'ingredient_results_screen.dart';

/// Pick or take a photo and identify vegetables on the device (no network).
class IngredientScannerScreen extends StatefulWidget {
  const IngredientScannerScreen({super.key});

  @override
  State<IngredientScannerScreen> createState() => _IngredientScannerScreenState();
}

class _IngredientScannerScreenState extends State<IngredientScannerScreen> {
  final _picker = ImagePicker();
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    // Warm the model up while the user frames the photo.
    if (YoloService.isSupported) YoloService.initialize().catchError((_) {});
  }

  bool get _cameraAvailable =>
      !kIsWeb && (defaultTargetPlatform == TargetPlatform.android || defaultTargetPlatform == TargetPlatform.iOS);

  Future<void> _pick(ImageSource source) async {
    setState(() => _error = null);
    XFile? file;
    try {
      // The model works at 640 px, so a 1600 px photo keeps detail while
      // making decoding much faster than a full 12 MP image.
      file = await _picker.pickImage(source: source, maxWidth: 1600, maxHeight: 1600, imageQuality: 92);
    } catch (e) {
      setState(() => _error = source == ImageSource.camera
          ? 'Camera unavailable. Check that PantryPilot has camera permission in your phone settings.'
          : 'Could not open your photos. Check that PantryPilot has photo access.');
      return;
    }
    if (file == null) return;

    setState(() => _busy = true);
    try {
      final bytes = await file.readAsBytes();
      final result = await YoloService.detect(bytes);
      if (!mounted) return;
      await Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => IngredientResultsScreen(imageBytes: bytes, result: result),
      ));
    } on FormatException catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      debugPrint('Detection failed: $e');
      setState(() => _error = 'Detection failed on this device. Please try another photo.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Scan vegetables')),
      body: SafeArea(
        child: ListView(
          padding: EdgeInsets.only(bottom: 24 + MediaQuery.paddingOf(context).bottom),
          children: [
            ContentWidth(
              maxWidth: 560,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SizedBox(height: 8),
                  AppCard(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      children: [
                        const IconBadge(icon: Icons.center_focus_strong_rounded, size: 64),
                        const SizedBox(height: 14),
                        Text('Identify vegetables from a photo', style: t.titleMedium, textAlign: TextAlign.center),
                        const SizedBox(height: 6),
                        Text(
                          'Runs entirely on your device — no internet needed. You review the results before anything is saved.',
                          style: t.bodyMedium,
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (!YoloService.isSupported)
                    const ErrorState(message: 'On-device detection is not available in the web version.', compact: true)
                  else if (_busy)
                    const LoadingView(label: 'Looking for vegetables…')
                  else ...[
                    if (_cameraAvailable) ...[
                      FilledButton.icon(
                        onPressed: () => _pick(ImageSource.camera),
                        icon: const Icon(Icons.photo_camera_outlined),
                        label: const Text('Take a photo'),
                      ),
                      const SizedBox(height: 10),
                    ],
                    OutlinedButton.icon(
                      onPressed: () => _pick(ImageSource.gallery),
                      icon: const Icon(Icons.photo_library_outlined),
                      label: Text(_cameraAvailable ? 'Choose from gallery' : 'Choose a photo'),
                    ),
                  ],
                  if (_error != null) ...[
                    const SizedBox(height: 16),
                    ErrorState(message: _error!, compact: true),
                  ],
                  const SectionTitle('Tips for better results'),
                  for (final tip in const [
                    'Good, even lighting — avoid strong shadows.',
                    'Fill the frame with the vegetables; keep them in focus.',
                    'Spread items out so they don\'t completely overlap.',
                  ])
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Icon(Icons.check_rounded, size: 18, color: AppTheme.primaryColor),
                        const SizedBox(width: 8),
                        Expanded(child: Text(tip, style: t.bodyMedium)),
                      ]),
                    ),
                  const SizedBox(height: 8),
                  Text(
                    'Recognises 22 vegetables: ${YoloService.labels.isEmpty ? 'tomato, potato, carrot, cabbage, cauliflower and more' : YoloService.labels.map(YoloService.formatClassName).join(', ')}.',
                    style: t.bodySmall,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
