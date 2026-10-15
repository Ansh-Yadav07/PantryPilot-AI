import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../services/api_client.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/ui.dart';

const kExpenseCategories = [
  'Groceries', 'Vegetables', 'Fruits', 'Dairy', 'Bakery & Grains',
  'Meat & Seafood', 'Snacks & Beverages', 'Pantry Staples', 'Other',
];

/// Spending, pantry health and AI insights for the signed-in user.
class SmartDashboardScreen extends StatefulWidget {
  const SmartDashboardScreen({super.key});

  @override
  State<SmartDashboardScreen> createState() => _SmartDashboardScreenState();
}

class _SmartDashboardScreenState extends State<SmartDashboardScreen> {
  Map<String, dynamic>? _expenses;
  Map<String, dynamic>? _analytics;
  String? _error;
  bool _loading = true;

  List<Map<String, dynamic>>? _insights;
  String? _insightSource;
  String? _insightError;
  bool _insightLoading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await Future.wait([ApiService.getExpenses(), ApiService.getAnalytics()]);
      if (!mounted) return;
      setState(() {
        _expenses = results[0];
        _analytics = results[1];
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loadInsights() async {
    setState(() {
      _insightLoading = true;
      _insightError = null;
    });
    try {
      final r = await ApiService.getInsights();
      if (!mounted) return;
      setState(() {
        _insights = (r['insights'] as List? ?? []).map((e) => Map<String, dynamic>.from(e as Map)).toList();
        _insightSource = r['source']?.toString();
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _insightError = e.message);
    } finally {
      if (mounted) setState(() => _insightLoading = false);
    }
  }

  Future<void> _delete(Map<String, dynamic> e) async {
    final ok = await confirmDialog(context,
        title: 'Delete expense?',
        message: '${e['title']} · ${formatMoney((e['amount'] as num?) ?? 0)}',
        confirmLabel: 'Delete',
        destructive: true);
    if (!ok) return;
    try {
      await ApiService.deleteExpense(e['id'].toString());
      await _load();
    } on ApiException catch (err) {
      if (mounted) showAppSnack(context, err.message, error: true);
    }
  }

  Future<void> _addExpense() async {
    final added = await showAppSheet<bool>(context, builder: (_) => const _AddExpenseForm());
    if (added == true) {
      await _load();
      if (mounted) showAppSnack(context, 'Expense added');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Insights & expenses')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _addExpense,
        icon: const Icon(Icons.add_rounded),
        label: const Text('Expense'),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: EdgeInsets.only(bottom: 96 + MediaQuery.paddingOf(context).bottom),
          children: [
            ContentWidth(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (_loading && _expenses == null)
                    const LoadingView()
                  else if (_error != null && _expenses == null)
                    ErrorState(message: _error!, onRetry: _load)
                  else ...[
                    if (_error != null) ErrorState(message: _error!, onRetry: _load, compact: true),
                    _spending(t),
                    _pantryHealth(t),
                    _insightsSection(t),
                    _expenseList(t),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _spending(TextTheme t) {
    final e = _expenses!;
    final weekly = (e['weekly_spending'] as List? ?? const [0, 0, 0, 0]).map((v) => (v as num).toDouble()).toList();
    final cats = (e['category_breakdown'] as List? ?? []).map((c) => Map<String, dynamic>.from(c as Map)).toList();
    final maxY = weekly.fold<double>(0, (a, b) => b > a ? b : a);

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const SectionTitle('Spending'),
      ResponsiveGrid(minItemWidth: 150, children: [
        StatTile(
          icon: Icons.calendar_today_rounded,
          label: 'This month',
          value: formatMoney((e['total_this_month'] as num?) ?? 0),
          color: AppTheme.accentColor,
        ),
        StatTile(
          icon: Icons.history_rounded,
          label: 'Last month',
          value: formatMoney((e['total_last_month'] as num?) ?? 0),
          color: AppTheme.secondaryColor,
        ),
      ]),
      if (_analytics?['spend_comparison'] != null) ...[
        const SizedBox(height: 8),
        Text(_analytics!['spend_comparison'].toString(), style: t.bodySmall),
      ],
      const SizedBox(height: 12),
      AppCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Last 4 weeks', style: t.titleSmall),
          const SizedBox(height: 16),
          SizedBox(
            height: 170,
            child: maxY == 0
                ? Center(child: Text('No spending recorded in the last 4 weeks', style: t.bodySmall, textAlign: TextAlign.center))
                : BarChart(BarChartData(
                    maxY: maxY * 1.2,
                    gridData: const FlGridData(show: false),
                    borderData: FlBorderData(show: false),
                    barTouchData: BarTouchData(
                      touchTooltipData: BarTouchTooltipData(
                        getTooltipItem: (g, _, rod, __) =>
                            BarTooltipItem(formatMoney(rod.toY), const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                      ),
                    ),
                    titlesData: FlTitlesData(
                      leftTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                      rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                      topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                      bottomTitles: AxisTitles(
                        sideTitles: SideTitles(
                          showTitles: true,
                          reservedSize: 28,
                          getTitlesWidget: (v, _) => Padding(
                            padding: const EdgeInsets.only(top: 6),
                            child: Text(const ['3 wks ago', '2 wks ago', 'Last week', 'This week'][v.toInt()],
                                style: const TextStyle(fontSize: 11, color: AppTheme.textSecondaryColor)),
                          ),
                        ),
                      ),
                    ),
                    barGroups: [
                      for (var i = 0; i < weekly.length; i++)
                        BarChartGroupData(x: i, barRods: [
                          BarChartRodData(
                            toY: weekly[i],
                            width: 22,
                            color: i == 3 ? AppTheme.primaryColor : AppTheme.secondaryColor.withValues(alpha: 0.55),
                            borderRadius: const BorderRadius.vertical(top: Radius.circular(6)),
                          ),
                        ]),
                    ],
                  )),
          ),
          if (cats.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text('This month by category', style: t.titleSmall),
            const SizedBox(height: 8),
            for (final c in cats)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 5),
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  Wrap(alignment: WrapAlignment.spaceBetween, spacing: 8, children: [
                    Text(c['category'].toString(), style: t.bodyMedium),
                    Text(formatMoney((c['amount'] as num?) ?? 0), style: t.titleSmall),
                  ]),
                  const SizedBox(height: 4),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(
                      value: (((c['percentage'] as num?) ?? 0) / 100).clamp(0.0, 1.0).toDouble(),
                      minHeight: 6,
                      backgroundColor: AppTheme.surfaceMuted,
                      color: AppTheme.accentColor,
                    ),
                  ),
                ]),
              ),
          ],
        ]),
      ),
    ]);
  }

  Widget _pantryHealth(TextTheme t) {
    final a = _analytics;
    if (a == null) return const SizedBox.shrink();
    final risk = (a['at_risk_items'] as List? ?? []).map((e) => Map<String, dynamic>.from(e as Map)).toList();
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const SectionTitle('Pantry health'),
      ResponsiveGrid(minItemWidth: 110, children: [
        StatTile(icon: Icons.eco_outlined, label: 'Fresh', value: '${a['fresh_items_count'] ?? 0}'),
        StatTile(
            icon: Icons.schedule_rounded, label: 'Use soon', value: '${a['expiring_soon_count'] ?? 0}', color: AppTheme.warningColor),
        StatTile(icon: Icons.delete_outline_rounded, label: 'Expired', value: '${a['expired_count'] ?? 0}', color: AppTheme.dangerColor),
      ]),
      const SizedBox(height: 12),
      AppCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Waste risk', style: t.titleSmall),
          const SizedBox(height: 2),
          Text('Rule-based: high risk = expires within 3 days or already expired.', style: t.bodySmall),
          const SizedBox(height: 10),
          if (risk.isEmpty)
            Text('No items at high risk of being wasted.', style: t.bodyMedium)
          else
            for (final r in risk)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(children: [
                  Text(r['emoji']?.toString() ?? '•', style: const TextStyle(fontSize: 18), textScaler: TextScaler.noScaling),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${r['name']}', style: t.bodyMedium, maxLines: 2, overflow: TextOverflow.ellipsis),
                      const SizedBox(height: 2),
                      StatusPill(
                        label: '${r['risk_level'] == 'CRITICAL' ? 'Expired' : 'High risk'} · ${r['expiry_display']}',
                        color: AppTheme.dangerColor,
                        background: AppTheme.dangerLight,
                      ),
                    ]),
                  ),
                ]),
              ),
        ]),
      ),
    ]);
  }

  Widget _insightsSection(TextTheme t) {
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      SectionTitle('Personal insights', actionLabel: _insights == null ? null : 'Refresh', onAction: _insightLoading ? null : _loadInsights),
      if (_insightLoading)
        const LoadingView(label: 'Analysing your pantry and spending…')
      else if (_insightError != null)
        ErrorState(message: _insightError!, onRetry: _loadInsights, compact: true)
      else if (_insights == null)
        AppCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              const IconBadge(icon: Icons.auto_awesome_rounded, size: 40),
              const SizedBox(width: 12),
              Expanded(child: Text('Get tips based on your pantry and spending.', style: t.bodyMedium)),
            ]),
            const SizedBox(height: 12),
            FilledButton.tonal(onPressed: _loadInsights, child: const Text('Generate insights')),
          ]),
        )
      else ...[
        for (final i in _insights!)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: AppCard(
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                IconBadge(emoji: (i['emoji'] ?? '💡').toString(), size: 40, color: AppTheme.accentColor),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(i['title']?.toString() ?? '', style: t.titleSmall),
                    const SizedBox(height: 4),
                    Text(i['description']?.toString() ?? '', style: t.bodyMedium),
                  ]),
                ),
              ]),
            ),
          ),
        Text(
          _insightSource == 'gemini' ? 'Generated by Gemini AI from your data.' : 'AI unavailable — summary based on your data.',
          style: t.bodySmall,
        ),
      ],
    ]);
  }

  Widget _expenseList(TextTheme t) {
    final list = (_expenses!['expenses'] as List? ?? []).map((e) => Map<String, dynamic>.from(e as Map)).toList();
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const SectionTitle('Recent expenses'),
      if (list.isEmpty)
        AppCard(
          child: EmptyState(
            icon: Icons.receipt_long_outlined,
            title: 'No expenses yet',
            message: 'Add an expense or scan a receipt to track your grocery spending.',
            actionLabel: 'Add expense',
            onAction: _addExpense,
          ),
        )
      else
        AppCard(
          padding: EdgeInsets.zero,
          child: Column(children: [
            for (var i = 0; i < list.length; i++) ...[
              if (i > 0) const Divider(indent: 16, endIndent: 16),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 10, 4, 10),
                child: Row(children: [
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(list[i]['title']?.toString() ?? '', style: t.titleSmall, maxLines: 2, overflow: TextOverflow.ellipsis),
                      const SizedBox(height: 2),
                      Text(formatMoney((list[i]['amount'] as num?) ?? 0), style: t.titleMedium),
                      Text('${_fmtDate(list[i]['date'])} · ${list[i]['category'] ?? ''}',
                          style: t.bodySmall, maxLines: 1, overflow: TextOverflow.ellipsis),
                    ]),
                  ),
                  IconButton(
                    tooltip: 'Delete expense',
                    icon: const Icon(Icons.delete_outline_rounded, size: 20),
                    onPressed: () => _delete(list[i]),
                  ),
                ]),
              ),
            ],
          ]),
        ),
    ]);
  }

  static String _fmtDate(dynamic d) {
    final p = DateTime.tryParse(d?.toString() ?? '');
    return p == null ? '' : DateFormat('d MMM yyyy').format(p);
  }
}

class _AddExpenseForm extends StatefulWidget {
  const _AddExpenseForm();

  @override
  State<_AddExpenseForm> createState() => _AddExpenseFormState();
}

class _AddExpenseFormState extends State<_AddExpenseForm> {
  final _formKey = GlobalKey<FormState>();
  final _title = TextEditingController();
  final _amount = TextEditingController();
  String _category = 'Groceries';
  DateTime _date = DateTime.now();
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _title.dispose();
    _amount.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate() || _saving) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await ApiService.addExpense(
        title: _title.text.trim(),
        amount: double.parse(_amount.text.trim().replaceAll(',', '')),
        category: _category,
        date: _date,
      );
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _formKey,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text('Add expense', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 16),
        TextFormField(
          controller: _title,
          textCapitalization: TextCapitalization.sentences,
          decoration: const InputDecoration(labelText: 'Description', hintText: 'e.g. Weekly vegetables'),
          validator: (v) => (v ?? '').trim().isEmpty ? 'Enter a description' : null,
        ),
        const SizedBox(height: 12),
        TextFormField(
          controller: _amount,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(labelText: 'Amount', prefixText: '₹ '),
          validator: (v) {
            final x = double.tryParse((v ?? '').trim().replaceAll(',', ''));
            return (x == null || x <= 0) ? 'Enter an amount greater than 0' : null;
          },
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: _category,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Category'),
          items: [for (final c in kExpenseCategories) DropdownMenuItem(value: c, child: Text(c))],
          onChanged: (v) => setState(() => _category = v ?? _category),
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
            decoration: const InputDecoration(labelText: 'Date', prefixIcon: Icon(Icons.event_outlined)),
            child: Text(DateFormat('d MMM yyyy').format(_date)),
          ),
        ),
        if (_error != null) ...[const SizedBox(height: 12), Text(_error!, style: const TextStyle(color: AppTheme.dangerColor))],
        const SizedBox(height: 20),
        LoadingButton(label: 'Save expense', loading: _saving, onPressed: _save),
      ]),
    );
  }
}
