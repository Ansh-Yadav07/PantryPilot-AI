import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../services/api_client.dart';
import '../../services/api_service.dart';
import '../../services/pantry_provider.dart';
import '../../theme/app_theme.dart';
import '../../widgets/ui.dart';
import '../pantry/pantry_sheets.dart';

class _Line {
  bool include;
  final TextEditingController name;
  final TextEditingController qty;
  String unit;
  final double? price;
  final String category;
  final String? emoji;

  _Line(Map<String, dynamic> j)
      : include = !const {'Household', 'Other'}.contains(j['category']),
        name = TextEditingController(text: (j['name'] ?? '').toString()),
        qty = TextEditingController(text: j['quantity'] == null ? '' : formatQty((j['quantity'] as num).toDouble())),
        unit = kUnits.contains(j['unit']) ? j['unit'] as String : 'pcs',
        price = (j['price'] as num?)?.toDouble(),
        category = (j['category'] ?? 'Other').toString(),
        emoji = j['emoji']?.toString();

  void dispose() {
    name.dispose();
    qty.dispose();
  }
}

/// Review screen: the user checks every extracted value before saving.
class ReceiptConfirmationScreen extends StatefulWidget {
  final Map<String, dynamic> receipt;
  const ReceiptConfirmationScreen({super.key, required this.receipt});

  @override
  State<ReceiptConfirmationScreen> createState() => _ReceiptConfirmationScreenState();
}

class _ReceiptConfirmationScreenState extends State<ReceiptConfirmationScreen> {
  final _formKey = GlobalKey<FormState>();
  late final List<_Line> _lines;
  late final TextEditingController _store;
  late final TextEditingController _total;
  late DateTime _date;
  late final bool _dateFromReceipt;
  late String _totalSource;
  bool _recordExpense = true;
  bool _saving = false;
  String? _error;
  // Same key for every retry of this receipt: the server stores it once.
  final String _idempotencyKey = newIdempotencyKey();

  @override
  void initState() {
    super.initState();
    final r = widget.receipt;
    _lines = (r['items'] as List? ?? []).map((e) => _Line(Map<String, dynamic>.from(e as Map))).toList();
    _store = TextEditingController(text: (r['store_name'] ?? '').toString());
    final total = (r['total'] as num?) ?? (r['items_total'] as num?);
    _totalSource = r['total'] != null ? 'Read from receipt' : (r['items_total'] != null ? 'Sum of item prices' : 'Not found on receipt');
    final currency = r['currency']?.toString();
    if (currency != null && currency.isNotEmpty && currency != 'INR') {
      _totalSource = '$_totalSource · receipt is in $currency — enter the amount in ₹';
    }
    _total = TextEditingController(text: total == null ? '' : total.toStringAsFixed(2));
    final parsed = r['purchase_date'] != null ? DateTime.tryParse(r['purchase_date'].toString()) : null;
    _dateFromReceipt = parsed != null;
    _date = parsed ?? DateTime.now();
  }

  @override
  void dispose() {
    for (final l in _lines) {
      l.dispose();
    }
    _store.dispose();
    _total.dispose();
    super.dispose();
  }

  Future<void> _confirm() async {
    if (!_formKey.currentState!.validate()) return;
    final items = _lines.where((l) => l.include).toList();
    if (items.isEmpty && !_recordExpense) {
      setState(() => _error = 'Select at least one item or record the expense.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    final store = _store.text.trim();
    try {
      final res = await ApiService.confirmReceipt(
        idempotencyKey: _idempotencyKey,
        items: [
          for (final l in items) {'name': l.name.text.trim(), 'quantity': parseQty(l.qty.text), 'unit': l.unit, 'category': l.category},
        ],
        expense: _recordExpense
            ? {
                'title': store.isEmpty ? 'Grocery receipt' : store,
                'amount': double.parse(_total.text.trim().replaceAll(',', '')),
                'category': 'Groceries',
                'date': DateFormat('yyyy-MM-dd').format(_date),
              }
            : null,
      );
      if (!mounted) return;
      await context.read<PantryProvider>().load();
      if (!mounted) return;
      Navigator.of(context).popUntil((r) => r.isFirst);
      showAppSnack(
        context,
        res['duplicate'] == true
            ? 'This receipt was already saved.'
            : 'Saved ${items.length} item${items.length == 1 ? '' : 's'}${_recordExpense ? ' and the expense' : ''}',
      );
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final included = _lines.where((l) => l.include).length;
    return Scaffold(
      appBar: AppBar(title: const Text('Check your receipt')),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
          child: LoadingButton(
            label: included == 0 ? 'Save expense only' : 'Save $included item${included == 1 ? '' : 's'}',
            loading: _saving,
            onPressed: (included == 0 && !_recordExpense) ? null : _confirm,
          ),
        ),
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
          padding: EdgeInsets.only(bottom: 24 + MediaQuery.paddingOf(context).bottom),
          children: [
            ContentWidth(
              maxWidth: 720,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SizedBox(height: 8),
                  Text('Review everything we read before saving. Fix anything that looks wrong.', style: t.bodyMedium),
                  const SectionTitle('Bill'),
                  AppCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('Record as an expense'),
                          value: _recordExpense,
                          onChanged: _saving ? null : (v) => setState(() => _recordExpense = v),
                        ),
                        if (_recordExpense) ...[
                          const SizedBox(height: 8),
                          TextFormField(
                            controller: _store,
                            decoration: const InputDecoration(labelText: 'Store', hintText: 'e.g. Fresh Mart'),
                          ),
                          const SizedBox(height: 12),
                          TextFormField(
                            controller: _total,
                            keyboardType: const TextInputType.numberWithOptions(decimal: true),
                            decoration: InputDecoration(labelText: 'Total paid', prefixText: '₹ ', helperText: _totalSource),
                            validator: (v) {
                              final x = double.tryParse((v ?? '').trim().replaceAll(',', ''));
                              return (x == null || x <= 0) ? 'Enter the amount you paid' : null;
                            },
                          ),
                          const SizedBox(height: 12),
                          InkWell(
                            onTap: () async {
                              final d = await showDatePicker(
                                context: context,
                                initialDate: _date,
                                firstDate: DateTime.now().subtract(const Duration(days: 730)),
                                lastDate: DateTime.now(),
                              );
                              if (d != null) setState(() => _date = d);
                            },
                            child: InputDecorator(
                              decoration: InputDecoration(
                                labelText: 'Purchase date',
                                helperText: _dateFromReceipt ? 'Read from receipt' : 'Not found on receipt — please check',
                                prefixIcon: const Icon(Icons.event_outlined),
                              ),
                              child: Text(DateFormat('d MMM yyyy').format(_date)),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  SectionTitle('Items (${_lines.length})'),
                  Text('Ticked items are added to your pantry.', style: t.bodySmall),
                  const SizedBox(height: 10),
                  for (final l in _lines) _lineCard(l),
                  if (_error != null) ...[const SizedBox(height: 8), ErrorState(message: _error!, compact: true)],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _lineCard(_Line l) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: AppCard(
        padding: const EdgeInsets.fromLTRB(4, 10, 12, 12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Checkbox(value: l.include, onChanged: _saving ? null : (v) => setState(() => l.include = v ?? false)),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  TextFormField(
                    controller: l.name,
                    enabled: !_saving,
                    decoration: InputDecoration(labelText: 'Item', isDense: true, prefixText: l.emoji != null ? '${l.emoji}  ' : null),
                    validator: (v) => l.include && (v ?? '').trim().isEmpty ? 'Enter a name' : null,
                  ),
                  const SizedBox(height: 10),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: TextFormField(
                          controller: l.qty,
                          enabled: !_saving,
                          keyboardType: const TextInputType.numberWithOptions(decimal: true),
                          decoration: const InputDecoration(labelText: 'Qty', isDense: true),
                          validator: (v) => l.include && parseQty(v ?? '') == null ? 'Required' : null,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          initialValue: l.unit,
                          isExpanded: true,
                          isDense: true,
                          decoration: const InputDecoration(labelText: 'Unit', isDense: true),
                          items: [for (final u in kUnits) DropdownMenuItem(value: u, child: Text(u))],
                          onChanged: _saving ? null : (v) => setState(() => l.unit = v ?? l.unit),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    l.price == null ? 'Price not found' : 'Price ${formatMoney(l.price!)}',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(color: l.price == null ? AppTheme.warningColor : null),
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
