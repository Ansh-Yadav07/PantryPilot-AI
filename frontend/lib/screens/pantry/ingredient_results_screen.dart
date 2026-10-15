import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../services/api_client.dart';
import '../../services/pantry_provider.dart';
import '../../services/yolo_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/ui.dart';
import 'pantry_sheets.dart';

class _Group {
  String label;
  final int count;
  final double bestConfidence;
  bool selected = true;
  final TextEditingController qty;
  _Group(this.label, this.count, this.bestConfidence) : qty = TextEditingController(text: '$count');
}

/// Review on-device detections, correct them, then save to the cloud pantry.
class IngredientResultsScreen extends StatefulWidget {
  final Uint8List imageBytes;
  final DetectionResult result;
  const IngredientResultsScreen({super.key, required this.imageBytes, required this.result});

  @override
  State<IngredientResultsScreen> createState() => _IngredientResultsScreenState();
}

class _IngredientResultsScreenState extends State<IngredientResultsScreen> {
  late final List<_Group> _groups;
  final String _idempotencyKey = newIdempotencyKey();
  String? _error;

  @override
  void initState() {
    super.initState();
    final byLabel = <String, List<Detection>>{};
    for (final d in widget.result.detections) {
      byLabel.putIfAbsent(d.label, () => []).add(d);
    }
    _groups = byLabel.entries
        .map((e) => _Group(e.key, e.value.length, e.value.map((d) => d.confidence).reduce((a, b) => a > b ? a : b)))
        .toList()
      ..sort((a, b) => b.bestConfidence.compareTo(a.bestConfidence));
    for (final g in _groups) {
      g.selected = g.bestConfidence >= 0.4; // low-confidence guesses start unticked
    }
  }

  @override
  void dispose() {
    for (final g in _groups) {
      g.qty.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    final chosen = _groups.where((g) => g.selected).toList();
    if (chosen.isEmpty) return;
    for (final g in chosen) {
      if (parseQty(g.qty.text) == null) {
        setState(() => _error = 'Enter a valid quantity for ${YoloService.formatClassName(g.label)}.');
        return;
      }
    }
    setState(() => _error = null);
    try {
      await context.read<PantryProvider>().addItems(
        [for (final g in chosen) {'ingredient_id': g.label, 'quantity': parseQty(g.qty.text), 'unit': 'pcs'}],
        idempotencyKey: _idempotencyKey,
        source: 'scanner',
      );
      if (!mounted) return;
      Navigator.of(context).popUntil((r) => r.isFirst);
      showAppSnack(context, 'Saved ${chosen.length} item${chosen.length == 1 ? '' : 's'} to your pantry');
    } on ApiException catch (e) {
      setState(() => _error = '${e.message} Your scan is kept here — try again when you\'re online.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final saving = context.watch<PantryProvider>().isSaving;
    final r = widget.result;
    final selectedCount = _groups.where((g) => g.selected).length;

    return Scaffold(
      appBar: AppBar(title: const Text('Review results')),
      bottomNavigationBar: _groups.isEmpty
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                child: LoadingButton(
                  label: selectedCount == 0 ? 'Select items to save' : 'Save $selectedCount to pantry',
                  icon: Icons.cloud_upload_outlined,
                  loading: saving,
                  onPressed: selectedCount == 0 ? null : _save,
                ),
              ),
            ),
      body: ListView(
        padding: EdgeInsets.only(bottom: 24 + MediaQuery.paddingOf(context).bottom),
        children: [
          ContentWidth(
            maxWidth: 720,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const SizedBox(height: 8),
                ClipRRect(
                  borderRadius: BorderRadius.circular(AppTheme.radiusMd),
                  child: ConstrainedBox(
                    constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.45),
                    child: AspectRatio(
                      aspectRatio: r.imageWidth / r.imageHeight,
                      child: Stack(fit: StackFit.expand, children: [
                        Image.memory(widget.imageBytes, fit: BoxFit.fill, gaplessPlayback: true),
                        CustomPaint(painter: _BoxPainter(r)),
                      ]),
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Found ${r.detections.length} item${r.detections.length == 1 ? '' : 's'} on-device in ${(r.elapsed.inMilliseconds / 1000).toStringAsFixed(1)} s',
                  style: t.bodySmall,
                ),
                if (_groups.isEmpty)
                  EmptyState(
                    icon: Icons.search_off_rounded,
                    title: 'No vegetables found',
                    message: 'Try a closer, well-lit photo. The model recognises 22 common vegetables.',
                    actionLabel: 'Try another photo',
                    onAction: () => Navigator.pop(context),
                  )
                else ...[
                  const SectionTitle('Confirm what to add'),
                  for (final g in _groups) _groupTile(g, saving),
                  if (_error != null) ...[
                    const SizedBox(height: 8),
                    ErrorState(message: _error!, compact: true),
                  ],
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _groupTile(_Group g, bool saving) {
    final t = Theme.of(context).textTheme;
    final low = g.bestConfidence < 0.5;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: AppCard(
        padding: const EdgeInsets.fromLTRB(4, 8, 12, 8),
        child: Row(
          children: [
            Checkbox(value: g.selected, onChanged: saving ? null : (v) => setState(() => g.selected = v ?? false)),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  DropdownButton<String>(
                    value: g.label,
                    isExpanded: true,
                    isDense: true,
                    underline: const SizedBox.shrink(),
                    style: t.titleSmall,
                    items: [
                      for (final l in {...YoloService.labels, g.label})
                        DropdownMenuItem(value: l, child: Text(YoloService.formatClassName(l), overflow: TextOverflow.ellipsis)),
                    ],
                    onChanged: saving ? null : (v) => setState(() => g.label = v ?? g.label),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${(g.bestConfidence * 100).round()}% confidence${low ? ' · please check' : ''}',
                    style: t.bodySmall?.copyWith(color: low ? AppTheme.warningColor : null),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            SizedBox(
              width: 76,
              child: TextField(
                controller: g.qty,
                enabled: !saving,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                textAlign: TextAlign.center,
                decoration: const InputDecoration(labelText: 'Qty', suffixText: 'pcs', isDense: true),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BoxPainter extends CustomPainter {
  final DetectionResult r;
  _BoxPainter(this.r);

  @override
  void paint(Canvas canvas, Size size) {
    final sx = size.width / r.imageWidth, sy = size.height / r.imageHeight;
    final stroke = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5
      ..color = AppTheme.primaryColor;
    for (final d in r.detections) {
      final rect = Rect.fromLTRB(d.x1 * sx, d.y1 * sy, d.x2 * sx, d.y2 * sy);
      canvas.drawRRect(RRect.fromRectAndRadius(rect, const Radius.circular(6)), stroke);
      final tp = TextPainter(
        text: TextSpan(
          text: ' ${d.displayName} ${(d.confidence * 100).round()}% ',
          style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600, backgroundColor: AppTheme.primaryColor),
        ),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: size.width);
      final dy = rect.top - tp.height < 0 ? rect.top : rect.top - tp.height;
      tp.paint(canvas, Offset(rect.left.clamp(0, size.width - tp.width), dy));
    }
  }

  @override
  bool shouldRepaint(covariant _BoxPainter old) => old.r != r;
}
