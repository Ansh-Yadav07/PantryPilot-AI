import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../main.dart';
import '../../services/api_client.dart';
import '../../services/api_service.dart';
import '../../services/pantry_provider.dart';
import '../../theme/app_theme.dart';
import '../../widgets/ui.dart';

class MealPlannerScreen extends StatefulWidget {
  const MealPlannerScreen({super.key});

  @override
  State<MealPlannerScreen> createState() => _MealPlannerScreenState();
}

class _MealPlannerScreenState extends State<MealPlannerScreen> {
  static const _mealTypes = ['breakfast', 'lunch', 'dinner'];

  List<Map<String, dynamic>> _days = [];
  int _selected = 0;
  bool _loading = true;
  bool _generating = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _apply(Map<String, dynamic> res) {
    _days = (res['days'] as List? ?? []).map((e) => Map<String, dynamic>.from(e as Map)).toList();
    final todayIdx = _days.indexWhere((d) => d['is_today'] == true);
    _selected = todayIdx >= 0 ? todayIdx : 0;
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final res = await ApiService.getMealPlan();
      if (mounted) setState(() => _apply(res));
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _generate() async {
    if (_days.isNotEmpty) {
      final ok = await confirmDialog(context,
          title: 'Create a new plan?', message: 'Your current meal plan will be replaced.', confirmLabel: 'Create');
      if (!ok) return;
    }
    setState(() {
      _generating = true;
      _error = null;
    });
    try {
      final res = await ApiService.generateMealPlan();
      if (mounted) setState(() => _apply(res));
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _generating = false);
    }
  }

  Future<void> _reset() async {
    final ok = await confirmDialog(context,
        title: 'Clear meal plan?', message: 'This removes your whole plan.', confirmLabel: 'Clear', destructive: true);
    if (!ok) return;
    try {
      await ApiService.resetMealPlan();
      if (mounted) setState(() => _days = []);
    } on ApiException catch (e) {
      if (mounted) showAppSnack(context, e.message, error: true);
    }
  }

  Future<void> _rename(String date, String mealType, String current) async {
    final ctrl = TextEditingController(text: current);
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Change ${mealType[0].toUpperCase()}${mealType.substring(1)}'),
        content: TextField(controller: ctrl, autofocus: true, decoration: const InputDecoration(labelText: 'Meal')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, ctrl.text.trim()), child: const Text('Save')),
        ],
      ),
    );
    ctrl.dispose();
    if (name == null || name.isEmpty || name == current) return;
    try {
      final res = await ApiService.updateMeal(date: date, mealType: mealType, name: name);
      if (mounted) setState(() => _days = (res['days'] as List).map((e) => Map<String, dynamic>.from(e as Map)).toList());
    } on ApiException catch (e) {
      if (mounted) showAppSnack(context, e.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final pantryEmpty = context.watch<PantryProvider>().inStock.isEmpty;

    Widget body;
    if (_loading) {
      body = const LoadingView();
    } else if (_generating) {
      body = const LoadingView(label: 'Planning 7 days of meals from your pantry… this can take a minute.');
    } else if (_days.isEmpty) {
      body = Column(children: [
        if (_error != null) ...[ErrorState(message: _error!, compact: true), const SizedBox(height: 12)],
        AppCard(
          child: EmptyState(
            icon: Icons.calendar_month_outlined,
            title: 'No meal plan yet',
            message: pantryEmpty
                ? 'Add items to your pantry, then create a week of meals that uses them up.'
                : 'Create a 7-day plan that uses up what’s in your pantry, soonest-expiring first.',
            actionLabel: pantryEmpty ? 'Go to pantry' : 'Create meal plan',
            onAction: pantryEmpty ? () => openSection(context, AppSection.pantry) : _generate,
          ),
        ),
      ]);
    } else {
      final day = _days[_selected.clamp(0, _days.length - 1)];
      body = Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        if (_error != null) ...[ErrorState(message: _error!, compact: true), const SizedBox(height: 12)],
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(children: [
            for (var i = 0; i < _days.length; i++) Padding(
              padding: EdgeInsets.only(right: i == _days.length - 1 ? 0 : 8),
              child: Builder(builder: (_) {
              final d = _days[i];
              final sel = i == _selected;
              return InkWell(
                borderRadius: BorderRadius.circular(AppTheme.radiusMd),
                onTap: () => setState(() => _selected = i),
                child: Container(
                  constraints: const BoxConstraints(minWidth: 60),
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
                  decoration: BoxDecoration(
                    color: sel ? AppTheme.primaryColor : AppTheme.cardSurface,
                    borderRadius: BorderRadius.circular(AppTheme.radiusMd),
                    border: Border.all(color: sel ? AppTheme.primaryColor : AppTheme.borderColor),
                  ),
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Text((d['day_short'] ?? '').toString(),
                        style: TextStyle(fontSize: 12, color: sel ? Colors.white : AppTheme.textSecondaryColor)),
                    const SizedBox(height: 2),
                    Text('${d['day_number'] ?? ''}',
                        style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: sel ? Colors.white : AppTheme.textPrimaryColor)),
                  ]),
                ),
              );
              }),
            ),
          ]),
        ),
        const SizedBox(height: 8),
        for (final type in _mealTypes) _mealCard(day, type, t),
      ]);
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Meal planner'),
        actions: [
          if (_days.isNotEmpty && !_generating)
            PopupMenuButton<String>(
              onSelected: (v) => v == 'new' ? _generate() : _reset(),
              itemBuilder: (_) => const [
                PopupMenuItem(value: 'new', child: Text('Create new plan')),
                PopupMenuItem(value: 'clear', child: Text('Clear plan')),
              ],
            ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: EdgeInsets.only(bottom: 32 + MediaQuery.paddingOf(context).bottom),
          children: [ContentWidth(maxWidth: 820, child: Padding(padding: const EdgeInsets.only(top: 8), child: body))],
        ),
      ),
    );
  }

  Widget _mealCard(Map<String, dynamic> day, String type, TextTheme t) {
    final meal = Map<String, dynamic>.from((day[type] as Map?) ?? const {});
    final name = (meal['name'] ?? '').toString();
    final image = meal['image_url']?.toString();
    final used = (meal['ingredients_used'] as List? ?? []).map((e) => e.toString()).toList();
    final missing = (meal['missing_ingredients'] as List? ?? []).map((e) => e.toString()).toList();
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: AppCard(
        padding: EdgeInsets.zero,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          if (image != null && image.isNotEmpty)
            Stack(children: [
              AspectRatio(
                aspectRatio: 21 / 9,
                child: Image.network(image, fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => Container(color: AppTheme.surfaceMuted)),
              ),
              if (meal['image_is_illustrative'] == true)
                Positioned(
                  right: 8,
                  bottom: 8,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(color: Colors.black54, borderRadius: BorderRadius.circular(4)),
                    child: const Text('Illustration', style: TextStyle(color: Colors.white, fontSize: 11)),
                  ),
                ),
            ]),
          Padding(
            padding: const EdgeInsets.all(14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Expanded(
                  child: Text(type.toUpperCase(),
                      style: t.labelSmall?.copyWith(letterSpacing: 0.8, color: AppTheme.primaryColor, fontWeight: FontWeight.w700)),
                ),
                IconButton(
                  tooltip: 'Change meal',
                  visualDensity: VisualDensity.compact,
                  onPressed: () => _rename(day['date'].toString(), type, name),
                  icon: const Icon(Icons.edit_outlined, size: 18),
                ),
              ]),
              Text(name.isEmpty ? '—' : name, style: t.titleMedium),
              if ((meal['description'] ?? '').toString().isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(meal['description'].toString(), style: t.bodySmall),
              ],
              const SizedBox(height: 8),
              Wrap(spacing: 6, runSpacing: 6, children: [
                if ((meal['prep_time'] ?? '').toString().isNotEmpty)
                  StatusPill(label: meal['prep_time'].toString(), color: AppTheme.textSecondaryColor, background: AppTheme.surfaceMuted),
                if ((meal['calories'] ?? '').toString().isNotEmpty)
                  StatusPill(label: meal['calories'].toString(), color: AppTheme.textSecondaryColor, background: AppTheme.surfaceMuted),
                if (meal['uses_expiring_items'] == true)
                  const StatusPill(label: 'Uses expiring items', color: AppTheme.warningColor, background: AppTheme.warningLight),
              ]),
              if (used.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text('From pantry: ${used.join(', ')}', style: t.bodySmall),
              ],
              if (missing.isNotEmpty) ...[
                const SizedBox(height: 2),
                Text('To buy: ${missing.join(', ')}', style: t.bodySmall?.copyWith(color: AppTheme.warningColor)),
              ],
            ]),
          ),
        ]),
      ),
    );
  }
}
