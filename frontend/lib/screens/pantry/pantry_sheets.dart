import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../models/pantry_item.dart';
import '../../services/api_client.dart';
import '../../services/pantry_provider.dart';
import '../../theme/app_theme.dart';
import '../../widgets/ui.dart';

const kUnits = ['pcs', 'g', 'kg', 'ml', 'l', 'pack'];

String formatQty(double q) => q == q.roundToDouble() ? q.toInt().toString() : q.toStringAsFixed(2).replaceFirst(RegExp(r'0$'), '');

double? parseQty(String s) {
  final v = double.tryParse(s.trim().replaceAll(',', '.'));
  return (v == null || v.isNaN || v <= 0 || v > 100000) ? null : v;
}

Future<void> showAddItemSheet(BuildContext context, {String? presetName}) {
  return showAppSheet(context, builder: (_) => ChangeNotifierProvider.value(
        value: context.read<PantryProvider>(),
        child: _AddItemForm(presetName: presetName),
      ));
}

Future<void> showItemSheet(BuildContext context, PantryItem item) {
  return showAppSheet(context, builder: (_) => ChangeNotifierProvider.value(
        value: context.read<PantryProvider>(),
        child: _ItemDetail(item: item),
      ));
}

class _UnitDropdown extends StatelessWidget {
  final String value;
  final ValueChanged<String> onChanged;
  const _UnitDropdown({required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final options = kUnits.contains(value) ? kUnits : [...kUnits, value];
    return DropdownButtonFormField<String>(
      initialValue: value,
      isExpanded: true,
      decoration: const InputDecoration(labelText: 'Unit'),
      items: [for (final u in options) DropdownMenuItem(value: u, child: Text(u))],
      onChanged: (v) => v != null ? onChanged(v) : null,
    );
  }
}

class _ExpiryField extends StatelessWidget {
  final DateTime? value;
  final ValueChanged<DateTime?> onChanged;
  final String emptyLabel;
  const _ExpiryField({required this.value, required this.onChanged, required this.emptyLabel});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(AppTheme.radiusSm),
      onTap: () async {
        final now = DateTime.now();
        final picked = await showDatePicker(
          context: context,
          initialDate: value ?? now.add(const Duration(days: 7)),
          firstDate: now.subtract(const Duration(days: 365)),
          lastDate: now.add(const Duration(days: 365 * 3)),
          helpText: 'Expiry date',
        );
        if (picked != null) onChanged(picked);
      },
      child: InputDecorator(
        decoration: InputDecoration(
          labelText: 'Expiry date',
          prefixIcon: const Icon(Icons.event_outlined),
          suffixIcon: value == null
              ? null
              : IconButton(tooltip: 'Clear date', icon: const Icon(Icons.close_rounded), onPressed: () => onChanged(null)),
        ),
        child: Text(
          value == null ? emptyLabel : DateFormat('EEE, d MMM yyyy').format(value!),
          style: TextStyle(color: value == null ? AppTheme.textTertiaryColor : AppTheme.textPrimaryColor),
          overflow: TextOverflow.ellipsis,
        ),
      ),
    );
  }
}

class _AddItemForm extends StatefulWidget {
  final String? presetName;
  const _AddItemForm({this.presetName});

  @override
  State<_AddItemForm> createState() => _AddItemFormState();
}

class _AddItemFormState extends State<_AddItemForm> {
  final _formKey = GlobalKey<FormState>();
  // Owned by the Autocomplete field; captured in fieldViewBuilder.
  TextEditingController? _name;
  final _qty = TextEditingController(text: '1');
  String _unit = 'pcs';
  DateTime? _expiry;
  // One key per sheet: a retry after a network error can never add twice.
  final String _idempotencyKey = newIdempotencyKey();
  String? _error;

  @override
  void dispose() {
    _qty.dispose();
    super.dispose();
  }

  String get _nameText => (_name?.text ?? '').trim();

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    final pantry = context.read<PantryProvider>();
    setState(() => _error = null);
    try {
      await pantry.addItems([
        {
          'name': _nameText,
          'quantity': parseQty(_qty.text),
          'unit': _unit,
          if (_expiry != null) 'expiry_date': DateFormat('yyyy-MM-dd').format(_expiry!),
        }
      ], idempotencyKey: _idempotencyKey);
      if (!mounted) return;
      Navigator.pop(context);
      showAppSnack(context, 'Added $_nameText to your pantry');
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final pantry = context.watch<PantryProvider>();
    final names = pantry.items.where((i) => i.isCatalog).map((i) => i.name).toList();
    return Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Add to pantry', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 4),
          Text('Leave the expiry date empty to have it estimated for you.', style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 18),
          Autocomplete<String>(
            initialValue: TextEditingValue(text: widget.presetName ?? ''),
            optionsBuilder: (v) {
              final q = v.text.trim().toLowerCase();
              if (q.isEmpty) return const Iterable<String>.empty();
              return names.where((n) => n.toLowerCase().contains(q)).take(6);
            },
            fieldViewBuilder: (ctx, ctrl, focus, onSubmit) {
              _name = ctrl;
              return TextFormField(
                controller: ctrl,
                focusNode: focus,
                textCapitalization: TextCapitalization.sentences,
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(labelText: 'Item name', hintText: 'e.g. Tomato, Paneer, Rice'),
                validator: (v) => (v ?? '').trim().isEmpty ? 'Enter an item name' : null,
              );
            },
          ),
          const SizedBox(height: 14),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: TextFormField(
                  controller: _qty,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(labelText: 'Quantity'),
                  validator: (v) => parseQty(v ?? '') == null ? 'Enter a positive number' : null,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(child: _UnitDropdown(value: _unit, onChanged: (u) => setState(() => _unit = u))),
            ],
          ),
          const SizedBox(height: 14),
          _ExpiryField(value: _expiry, onChanged: (d) => setState(() => _expiry = d), emptyLabel: 'Estimate automatically'),
          if (_error != null) ...[
            const SizedBox(height: 14),
            Text(_error!, style: const TextStyle(color: AppTheme.dangerColor)),
          ],
          const SizedBox(height: 20),
          LoadingButton(label: 'Add item', icon: Icons.add_rounded, loading: pantry.isSaving, onPressed: _save),
        ],
      ),
    );
  }
}

class _ItemDetail extends StatefulWidget {
  final PantryItem item;
  const _ItemDetail({required this.item});

  @override
  State<_ItemDetail> createState() => _ItemDetailState();
}

class _ItemDetailState extends State<_ItemDetail> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _qty;
  late String _unit;
  late DateTime? _expiry;
  String? _error;
  final String _addKey = newIdempotencyKey();

  @override
  void initState() {
    super.initState();
    final i = widget.item;
    _qty = TextEditingController(text: i.inStock ? formatQty(i.totalQuantity) : '1');
    _unit = i.unit.isEmpty ? 'pcs' : i.unit;
    _expiry = i.earliestExpiry;
  }

  @override
  void dispose() {
    _qty.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() op, String success) async {
    setState(() => _error = null);
    try {
      await op();
      if (!mounted) return;
      Navigator.pop(context);
      showAppSnack(context, success);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    final pantry = context.read<PantryProvider>();
    await _run(() => pantry.updateItem(widget.item.id, quantity: parseQty(_qty.text)!, unit: _unit, expiry: _expiry),
        'Saved changes to ${widget.item.name}');
  }

  Future<void> _delete() async {
    final pantry = context.read<PantryProvider>();
    final ok = await confirmDialog(context,
        title: 'Remove ${widget.item.name}?',
        message: 'This removes all of its stock from your pantry.',
        confirmLabel: 'Remove',
        destructive: true);
    if (ok) await _run(() => pantry.deleteItem(widget.item.id), 'Removed ${widget.item.name}');
  }

  Future<void> _useSome() async {
    final pantry = context.read<PantryProvider>();
    final ctrl = TextEditingController();
    final amount = await showDialog<double>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('How much did you use?'),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(labelText: 'Amount', suffixText: _unit),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, parseQty(ctrl.text)), child: const Text('Update')),
        ],
      ),
    );
    ctrl.dispose();
    if (amount != null) await _run(() => pantry.consume(widget.item.id, amount, _unit), 'Updated ${widget.item.name}');
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    final pantry = context.watch<PantryProvider>();
    final t = Theme.of(context).textTheme;
    return Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              IconBadge(emoji: item.emoji, size: 52),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.name, style: t.titleLarge, maxLines: 2, overflow: TextOverflow.ellipsis),
                    const SizedBox(height: 4),
                    Text(item.inStock ? '${item.displayQuantity} · ${item.category}' : item.category, style: t.bodySmall),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Align(alignment: Alignment.centerLeft, child: StatusPill.forItem(item)),
          if (item.inStock && (item.storageTip.isNotEmpty || item.storageMethod.isNotEmpty)) ...[
            const SizedBox(height: 14),
            AppCard(
              color: AppTheme.surfaceMuted,
              borderColor: AppTheme.surfaceMuted,
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Storage: ${item.storageMethod.isEmpty ? '—' : item.storageMethod}',
                    style: t.titleSmall,
                  ),
                  if (item.storageTip.isNotEmpty) ...[const SizedBox(height: 4), Text(item.storageTip, style: t.bodySmall)],
                  const SizedBox(height: 6),
                  Text(
                    item.aiPredicted ? 'Expiry estimated by AI' : 'Expiry from typical shelf life or your input',
                    style: t.labelSmall,
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 18),
          Text(item.inStock ? 'Edit stock' : 'Add stock', style: t.titleMedium),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: TextFormField(
                  controller: _qty,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(labelText: 'Quantity'),
                  validator: (v) => parseQty(v ?? '') == null ? 'Enter a positive number' : null,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(child: _UnitDropdown(value: _unit, onChanged: (u) => setState(() => _unit = u))),
            ],
          ),
          const SizedBox(height: 14),
          _ExpiryField(
            value: _expiry,
            onChanged: (d) => setState(() => _expiry = d),
            emptyLabel: item.inStock ? 'No expiry date' : 'Estimate automatically',
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, style: const TextStyle(color: AppTheme.dangerColor)),
          ],
          const SizedBox(height: 20),
          if (item.inStock) ...[
            LoadingButton(label: 'Save changes', loading: pantry.isSaving, onPressed: _save),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: pantry.isSaving ? null : _useSome,
                    icon: const Icon(Icons.remove_circle_outline_rounded, size: 20),
                    label: const Text('Used some', overflow: TextOverflow.ellipsis),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(foregroundColor: AppTheme.dangerColor),
                    onPressed: pantry.isSaving ? null : _delete,
                    icon: const Icon(Icons.delete_outline_rounded, size: 20),
                    label: const Text('Remove', overflow: TextOverflow.ellipsis),
                  ),
                ),
              ],
            ),
          ] else
            LoadingButton(
              label: 'Add to pantry',
              icon: Icons.add_rounded,
              loading: pantry.isSaving,
              onPressed: () async {
                if (!_formKey.currentState!.validate()) return;
                await _run(
                  () => pantry.addItems([
                    {
                      'ingredient_id': item.id,
                      'quantity': parseQty(_qty.text),
                      'unit': _unit,
                      if (_expiry != null) 'expiry_date': DateFormat('yyyy-MM-dd').format(_expiry!),
                    }
                  ], idempotencyKey: _addKey),
                  'Added ${item.name}',
                );
              },
            ),
        ],
      ),
    );
  }
}
