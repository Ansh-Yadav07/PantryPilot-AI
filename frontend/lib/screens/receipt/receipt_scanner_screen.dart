import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../../services/api_client.dart';
import '../../services/api_service.dart';
import '../../widgets/ui.dart';
import 'receipt_confirmation_screen.dart';

/// Photograph a receipt; the backend reads it with Gemini. Nothing is saved
/// until the user reviews the result.
class ReceiptScannerScreen extends StatefulWidget {
  const ReceiptScannerScreen({super.key});

  @override
  State<ReceiptScannerScreen> createState() => _ReceiptScannerScreenState();
}

class _ReceiptScannerScreenState extends State<ReceiptScannerScreen> {
  final _picker = ImagePicker();
  bool _busy = false;
  String? _error;

  bool get _cameraAvailable =>
      !kIsWeb && (defaultTargetPlatform == TargetPlatform.android || defaultTargetPlatform == TargetPlatform.iOS);

  Future<void> _pick(ImageSource source) async {
    setState(() => _error = null);
    XFile? file;
    try {
      file = await _picker.pickImage(source: source, maxWidth: 2200, maxHeight: 2200, imageQuality: 88);
    } catch (_) {
      setState(() => _error = source == ImageSource.camera
          ? 'Camera unavailable. Check that PantryPilot has camera permission.'
          : 'Could not open your photos. Check that PantryPilot has photo access.');
      return;
    }
    if (file == null) return;
    setState(() => _busy = true);
    try {
      final bytes = await file.readAsBytes();
      final name = file.name.isNotEmpty ? file.name : 'receipt.jpg';
      final result = await ApiService.processReceipt(bytes, name);
      if (!mounted) return;
      await Navigator.of(context).push(MaterialPageRoute(builder: (_) => ReceiptConfirmationScreen(receipt: result)));
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Scan a receipt')),
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
                    child: Column(children: [
                      const IconBadge(icon: Icons.receipt_long_rounded, size: 64),
                      const SizedBox(height: 14),
                      Text('Add groceries from a receipt', style: t.titleMedium, textAlign: TextAlign.center),
                      const SizedBox(height: 6),
                      Text(
                        'We read the items, prices and total for you to check. Requires an internet connection.',
                        style: t.bodyMedium,
                        textAlign: TextAlign.center,
                      ),
                    ]),
                  ),
                  const SizedBox(height: 16),
                  if (_busy)
                    const LoadingView(label: 'Reading your receipt… this can take up to a minute.')
                  else ...[
                    if (_cameraAvailable) ...[
                      FilledButton.icon(
                        onPressed: () => _pick(ImageSource.camera),
                        icon: const Icon(Icons.photo_camera_outlined),
                        label: const Text('Photograph receipt'),
                      ),
                      const SizedBox(height: 10),
                    ],
                    OutlinedButton.icon(
                      onPressed: () => _pick(ImageSource.gallery),
                      icon: const Icon(Icons.photo_library_outlined),
                      label: const Text('Choose a photo'),
                    ),
                  ],
                  if (_error != null) ...[
                    const SizedBox(height: 16),
                    ErrorState(message: _error!, compact: true),
                  ],
                  const SectionTitle('For best results'),
                  Text(
                    'Lay the receipt flat in good light and capture the whole receipt, including the total.',
                    style: t.bodyMedium,
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
