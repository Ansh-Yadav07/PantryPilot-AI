import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../services/api_client.dart';
import '../../services/api_service.dart';
import '../../services/pantry_provider.dart';
import '../../services/shopping_provider.dart';
import '../../theme/app_theme.dart';
import '../../widgets/ui.dart';
import '../pantry/pantry_sheets.dart';

class RecipesScreen extends StatefulWidget {
  const RecipesScreen({super.key});

  @override
  State<RecipesScreen> createState() => _RecipesScreenState();
}

class _RecipesScreenState extends State<RecipesScreen> {
  static const _diets = ['Vegetarian', 'Vegan', 'Gluten-free', 'High protein', 'Low carb'];
  static const _times = <int?>[null, 15, 30, 45, 60];

  final Set<String> _selected = {};
  final Set<String> _dietSel = {};
  int _servings = 2;
  int? _maxTime;
  bool _loading = false;
  String? _error;
  String? _message;
  List<Map<String, dynamic>>? _recipes;
  // Recipes already shown this session; sent back so new suggestions differ.
  final List<String> _seen = [];

  Future<void> _generate() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
      _message = null;
    });
    try {
      final res = await ApiService.recommendRecipes(
        selectedIngredients: _selected.toList(),
        servings: _servings,
        maxCookingTime: _maxTime,
        dietaryPreferences: _dietSel.toList(),
        excludeRecipes: _seen.reversed.take(30).toList(),
      );
      setState(() {
        _recipes = (res['recipes'] as List? ?? []).map((e) => Map<String, dynamic>.from(e as Map)).toList();
        _message = res['message']?.toString();
        for (final r in _recipes!) {
          final name = r['name']?.toString();
          if (name != null && !_seen.contains(name)) _seen.add(name);
        }
      });
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final pantry = context.watch<PantryProvider>();
    final t = Theme.of(context).textTheme;
    final usable = pantry.inStock.where((i) => !i.isExpired).toList()
      ..sort((a, b) => (a.daysLeft ?? 9999).compareTo(b.daysLeft ?? 9999));

    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: EdgeInsets.only(bottom: 32 + MediaQuery.paddingOf(context).bottom),
          children: [
            ContentWidth(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const PageHeader(title: 'Recipes', subtitle: 'Ideas built from what’s in your pantry'),
                  if (pantry.hasLoaded && usable.isEmpty)
                    AppCard(
                      child: EmptyState(
                        icon: Icons.restaurant_menu_outlined,
                        title: 'Add ingredients first',
                        message: 'Recipe ideas are based on the items in your pantry that haven’t expired.',
                        actionLabel: 'Add an item',
                        onAction: () => showAddItemSheet(context),
                      ),
                    )
                  else
                    AppCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text('Ingredients', style: t.titleSmall),
                          const SizedBox(height: 4),
                          Text(
                            _selected.isEmpty
                                ? 'Using all ${usable.length} items, soonest-expiring first. Tap to choose specific ones.'
                                : 'Using ${_selected.length} selected item${_selected.length == 1 ? '' : 's'}.',
                            style: t.bodySmall,
                          ),
                          const SizedBox(height: 10),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              for (final i in usable)
                                FilterChip(
                                  avatar: Text(i.emoji, textScaler: TextScaler.noScaling),
                                  label: Text(i.name),
                                  selected: _selected.contains(i.id),
                                  onSelected: _loading
                                      ? null
                                      : (v) => setState(() => v ? _selected.add(i.id) : _selected.remove(i.id)),
                                ),
                            ],
                          ),
                          const SizedBox(height: 16),
                          Row(children: [
                            Expanded(child: Text('Servings', style: t.titleSmall)),
                            IconButton(
                              tooltip: 'Fewer servings',
                              onPressed: _servings > 1 ? () => setState(() => _servings--) : null,
                              icon: const Icon(Icons.remove_circle_outline_rounded),
                            ),
                            Text('$_servings', style: t.titleMedium),
                            IconButton(
                              tooltip: 'More servings',
                              onPressed: _servings < 12 ? () => setState(() => _servings++) : null,
                              icon: const Icon(Icons.add_circle_outline_rounded),
                            ),
                          ]),
                          const SizedBox(height: 8),
                          DropdownButtonFormField<int?>(
                            initialValue: _maxTime,
                            isExpanded: true,
                            decoration: const InputDecoration(labelText: 'Cooking time'),
                            items: [
                              for (final m in _times)
                                DropdownMenuItem(value: m, child: Text(m == null ? 'Any' : 'Under $m minutes')),
                            ],
                            onChanged: _loading ? null : (v) => setState(() => _maxTime = v),
                          ),
                          const SizedBox(height: 4),
                          const SizedBox(height: 8),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              for (final d in _diets)
                                FilterChip(
                                  label: Text(d),
                                  selected: _dietSel.contains(d),
                                  onSelected: _loading ? null : (v) => setState(() => v ? _dietSel.add(d) : _dietSel.remove(d)),
                                ),
                            ],
                          ),
                          const SizedBox(height: 16),
                          LoadingButton(
                            label: _recipes == null ? 'Suggest recipes' : 'Suggest new recipes',
                            icon: Icons.auto_awesome_rounded,
                            loading: _loading,
                            onPressed: usable.isEmpty ? null : _generate,
                          ),
                        ],
                      ),
                    ),
                  if (_loading) const LoadingView(label: 'Asking the AI chef… this can take up to a minute.'),
                  if (_error != null) ...[
                    const SizedBox(height: 16),
                    ErrorState(message: _error!, onRetry: _generate),
                  ],
                  if (!_loading && _message != null && (_recipes?.isEmpty ?? true)) ...[
                    const SizedBox(height: 16),
                    Text(_message!, style: t.bodyMedium, textAlign: TextAlign.center),
                  ],
                  if (!_loading && _recipes != null && _recipes!.isNotEmpty) ...[
                    const SectionTitle('Suggestions'),
                    ResponsiveGrid(
                      minItemWidth: 300,
                      children: [for (final r in _recipes!) _RecipeCard(recipe: r)],
                    ),
                    const SizedBox(height: 12),
                    Text('Recipes are AI-generated. Check ingredients for allergies and cook food thoroughly.',
                        style: t.bodySmall, textAlign: TextAlign.center),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

List<String> _strings(dynamic v) => (v as List? ?? const []).map((e) => e.toString()).toList();

class _RecipeCard extends StatelessWidget {
  final Map<String, dynamic> recipe;
  const _RecipeCard({required this.recipe});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final used = _strings(recipe['ingredients_used']);
    final missing = _strings(recipe['missing_ingredients']);
    return AppCard(
      onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => RecipeDetailScreen(recipe: recipe))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(recipe['name']?.toString() ?? 'Recipe', style: t.titleMedium, maxLines: 2, overflow: TextOverflow.ellipsis),
          if ((recipe['description'] ?? '').toString().isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(recipe['description'].toString(), style: t.bodySmall, maxLines: 3, overflow: TextOverflow.ellipsis),
          ],
          const SizedBox(height: 10),
          Wrap(spacing: 12, runSpacing: 6, children: [
            if ((recipe['prep_time'] ?? '').toString().isNotEmpty)
              _meta(Icons.timer_outlined, recipe['prep_time'].toString()),
            if ((recipe['difficulty'] ?? '').toString().isNotEmpty) _meta(Icons.bar_chart_rounded, recipe['difficulty'].toString()),
            if ((recipe['calories'] ?? '').toString().isNotEmpty)
              _meta(Icons.local_fire_department_outlined, recipe['calories'].toString()),
          ]),
          const SizedBox(height: 10),
          Wrap(spacing: 6, runSpacing: 6, children: [
            StatusPill(
                label: 'Uses ${used.length} pantry item${used.length == 1 ? '' : 's'}',
                color: AppTheme.primaryDark,
                background: AppTheme.lightGreen),
            if (missing.isNotEmpty)
              StatusPill(label: '${missing.length} to buy', color: AppTheme.warningColor, background: AppTheme.warningLight)
            else
              const StatusPill(label: 'Nothing to buy', color: AppTheme.primaryDark, background: AppTheme.lightGreen),
          ]),
        ],
      ),
    );
  }

  Widget _meta(IconData i, String s) => Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(i, size: 16, color: AppTheme.textSecondaryColor),
        const SizedBox(width: 4),
        Text(s, style: const TextStyle(fontSize: 13, color: AppTheme.textSecondaryColor)),
      ]);
}

class RecipeDetailScreen extends StatefulWidget {
  final Map<String, dynamic> recipe;
  const RecipeDetailScreen({super.key, required this.recipe});

  @override
  State<RecipeDetailScreen> createState() => _RecipeDetailScreenState();
}

class _RecipeDetailScreenState extends State<RecipeDetailScreen> {
  final Set<String> _added = {};
  bool _adding = false;

  Future<void> _addToList(List<String> names) async {
    if (_adding) return;
    setState(() => _adding = true);
    final shopping = context.read<ShoppingProvider>();
    try {
      for (final n in names.where((n) => !_added.contains(n))) {
        await shopping.add(n, source: 'recipe');
        _added.add(n);
      }
      if (mounted) showAppSnack(context, 'Added to your shopping list');
    } on ApiException catch (e) {
      if (mounted) showAppSnack(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _adding = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final r = widget.recipe;
    final t = Theme.of(context).textTheme;
    final used = _strings(r['ingredients_used']);
    final missing = _strings(r['missing_ingredients']);
    final steps = _strings(r['steps']);
    final image = r['image_url']?.toString();

    return Scaffold(
      appBar: AppBar(title: Text(r['name']?.toString() ?? 'Recipe', overflow: TextOverflow.ellipsis)),
      body: ListView(
        padding: EdgeInsets.only(bottom: 32 + MediaQuery.paddingOf(context).bottom),
        children: [
          ContentWidth(
            maxWidth: 760,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (image != null && image.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(AppTheme.radiusMd),
                    child: AspectRatio(
                      aspectRatio: 16 / 9,
                      child: Image.network(
                        image,
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => Container(
                          color: AppTheme.surfaceMuted,
                          child: const Icon(Icons.restaurant_rounded, size: 48, color: AppTheme.textTertiaryColor),
                        ),
                      ),
                    ),
                  ),
                ],
                const SizedBox(height: 12),
                Text(r['name']?.toString() ?? '', style: t.headlineSmall),
                if ((r['description'] ?? '').toString().isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Text(r['description'].toString(), style: t.bodyMedium),
                ],
                const SizedBox(height: 12),
                Wrap(spacing: 8, runSpacing: 8, children: [
                  for (final s in [r['prep_time'], r['difficulty'], r['calories'], '${r['servings'] ?? ''} servings'])
                    if (s != null && s.toString().trim().isNotEmpty && s.toString().trim() != 'servings')
                      Chip(label: Text(s.toString())),
                ]),
                const SectionTitle('From your pantry'),
                if (used.isEmpty) Text('—', style: t.bodyMedium),
                for (final u in used)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 3),
                    child: Row(children: [
                      const Icon(Icons.check_circle_rounded, size: 18, color: AppTheme.primaryColor),
                      const SizedBox(width: 8),
                      Expanded(child: Text(u, style: t.bodyLarge)),
                    ]),
                  ),
                if (missing.isNotEmpty) ...[
                  SectionTitle(
                    'You’ll need',
                    actionLabel: _added.containsAll(missing) ? null : 'Add all to list',
                    onAction: () => _addToList(missing),
                  ),
                  for (final m in missing)
                    Row(children: [
                      const Icon(Icons.shopping_basket_outlined, size: 18, color: AppTheme.warningColor),
                      const SizedBox(width: 8),
                      Expanded(child: Text(m, style: t.bodyLarge)),
                      _added.contains(m)
                          ? const Padding(
                              padding: EdgeInsets.all(12),
                              child: Icon(Icons.playlist_add_check_rounded, color: AppTheme.primaryColor),
                            )
                          : IconButton(
                              tooltip: 'Add $m to shopping list',
                              onPressed: _adding ? null : () => _addToList([m]),
                              icon: const Icon(Icons.add_shopping_cart_rounded),
                            ),
                    ]),
                ],
                const SectionTitle('Method'),
                if (steps.isEmpty) Text(r['instructions']?.toString() ?? '', style: t.bodyLarge),
                for (var i = 0; i < steps.length; i++)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 14),
                    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      CircleAvatar(
                        radius: 13,
                        backgroundColor: AppTheme.lightGreen,
                        child: Text('${i + 1}',
                            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppTheme.primaryDark)),
                      ),
                      const SizedBox(width: 12),
                      Expanded(child: Text(steps[i], style: t.bodyLarge)),
                    ]),
                  ),
                const SizedBox(height: 8),
                Text('Generated by AI from your pantry. Check for allergens before cooking.', style: t.bodySmall),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
