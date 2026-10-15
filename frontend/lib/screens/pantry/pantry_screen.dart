import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../models/pantry_item.dart';
import '../../services/api_client.dart';
import '../../services/pantry_provider.dart';
import '../../theme/app_theme.dart';
import '../../widgets/ui.dart';
import '../receipt/receipt_scanner_screen.dart';
import 'ingredient_scanner_screen.dart';
import 'pantry_sheets.dart';

enum _Filter { all, expiring, expired, missing }

class PantryScreen extends StatefulWidget {
  const PantryScreen({super.key});

  @override
  State<PantryScreen> createState() => _PantryScreenState();
}

class _PantryScreenState extends State<PantryScreen> {
  final _search = TextEditingController();
  _Filter _filter = _Filter.all;

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  List<PantryItem> _visible(PantryProvider p) {
    final q = _search.text.trim().toLowerCase();
    Iterable<PantryItem> list;
    switch (_filter) {
      case _Filter.all:
        list = p.inStock;
      case _Filter.expiring:
        list = p.expiringSoon;
      case _Filter.expired:
        list = p.expired;
      case _Filter.missing:
        list = p.notInStock;
    }
    if (q.isNotEmpty) {
      list = list.where((i) => i.name.toLowerCase().contains(q) || i.category.toLowerCase().contains(q));
    }
    final out = list.toList();
    if (_filter == _Filter.all) {
      out.sort((a, b) => (a.daysLeft ?? 99999).compareTo(b.daysLeft ?? 99999));
    }
    return out;
  }

  void _showAddMenu() {
    showModalBottomSheet(
      context: context,
      useSafeArea: true,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.center_focus_strong_rounded),
              title: const Text('Scan vegetables'),
              subtitle: const Text('Identified on your phone'),
              onTap: () {
                Navigator.pop(ctx);
                Navigator.of(context).push(MaterialPageRoute(builder: (_) => const IngredientScannerScreen()));
              },
            ),
            ListTile(
              leading: const Icon(Icons.receipt_long_rounded),
              title: const Text('Scan a receipt'),
              subtitle: const Text('Needs an internet connection'),
              onTap: () {
                Navigator.pop(ctx);
                Navigator.of(context).push(MaterialPageRoute(builder: (_) => const ReceiptScannerScreen()));
              },
            ),
            ListTile(
              leading: const Icon(Icons.edit_note_rounded),
              title: const Text('Add manually'),
              onTap: () {
                Navigator.pop(ctx);
                showAddItemSheet(context);
              },
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  Future<void> _refreshEstimates() async {
    final pantry = context.read<PantryProvider>();
    final ok = await confirmDialog(context,
        title: 'Re-estimate expiry dates?',
        message: 'Every item’s expiry date will be re-estimated from when it was added. Dates you set yourself will be replaced.',
        confirmLabel: 'Re-estimate');
    if (!ok) return;
    try {
      await pantry.refreshExpiry();
      if (mounted) showAppSnack(context, 'Expiry dates updated');
    } on ApiException catch (e) {
      if (mounted) showAppSnack(context, e.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final pantry = context.watch<PantryProvider>();
    final items = _visible(pantry);
    final counts = {
      _Filter.all: pantry.inStock.length,
      _Filter.expiring: pantry.expiringSoon.length,
      _Filter.expired: pantry.expired.length,
      _Filter.missing: pantry.notInStock.length,
    };
    const labels = {
      _Filter.all: 'In stock',
      _Filter.expiring: 'Expiring',
      _Filter.expired: 'Expired',
      _Filter.missing: 'Not in pantry',
    };

    Widget body;
    if (!pantry.hasLoaded && pantry.isLoading) {
      body = const LoadingView(label: 'Loading your pantry…');
    } else if (!pantry.hasLoaded && pantry.error != null) {
      body = ErrorState(message: pantry.error!, onRetry: pantry.load);
    } else if (items.isEmpty) {
      body = _emptyFor(pantry);
    } else {
      body = LayoutBuilder(builder: (context, c) {
        final cols = c.maxWidth >= 720 ? 2 : 1;
        if (cols == 1) {
          return Column(children: [
            for (final i in items) Padding(padding: const EdgeInsets.only(bottom: 10), child: _ItemCard(item: i)),
          ]);
        }
        return ResponsiveGrid(minItemWidth: 320, spacing: 10, children: [for (final i in items) _ItemCard(item: i)]);
      });
    }

    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _showAddMenu,
        icon: const Icon(Icons.add_rounded),
        label: const Text('Add'),
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: pantry.load,
          child: ListView(
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            padding: EdgeInsets.only(bottom: 96 + MediaQuery.paddingOf(context).bottom),
            children: [
              ContentWidth(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    PageHeader(
                      title: 'Pantry',
                      subtitle: '${pantry.inStock.length} ${pantry.inStock.length == 1 ? 'item' : 'items'} in stock',
                      actions: [
                        PopupMenuButton<String>(
                          tooltip: 'More',
                          onSelected: (v) => v == 'estimate' ? _refreshEstimates() : pantry.load(),
                          itemBuilder: (_) => const [
                            PopupMenuItem(value: 'refresh', child: Text('Refresh')),
                            PopupMenuItem(value: 'estimate', child: Text('Re-estimate expiry dates')),
                          ],
                        ),
                      ],
                    ),
                    if (pantry.error != null && pantry.hasLoaded) ...[
                      ErrorState(message: pantry.error!, onRetry: pantry.load, compact: true),
                      const SizedBox(height: 12),
                    ],
                    TextField(
                      controller: _search,
                      onChanged: (_) => setState(() {}),
                      textInputAction: TextInputAction.search,
                      decoration: InputDecoration(
                        hintText: 'Search your pantry',
                        prefixIcon: const Icon(Icons.search_rounded),
                        suffixIcon: _search.text.isEmpty
                            ? null
                            : IconButton(
                                tooltip: 'Clear search',
                                icon: const Icon(Icons.close_rounded),
                                onPressed: () => setState(_search.clear),
                              ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final f in _Filter.values)
                          ChoiceChip(
                            label: Text('${labels[f]} · ${counts[f]}'),
                            selected: _filter == f,
                            onSelected: (_) => setState(() => _filter = f),
                          ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    body,
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _emptyFor(PantryProvider p) {
    if (_search.text.isNotEmpty) {
      return const EmptyState(icon: Icons.search_off_rounded, title: 'No matches', message: 'Try a different search.');
    }
    switch (_filter) {
      case _Filter.all:
        return EmptyState(
          icon: Icons.kitchen_outlined,
          title: 'Nothing in your pantry yet',
          message: 'Scan vegetables or a receipt, or add items yourself.',
          actionLabel: 'Add items',
          onAction: _showAddMenu,
        );
      case _Filter.expiring:
        return const EmptyState(
            icon: Icons.check_circle_outline_rounded, title: 'Nothing expiring soon', message: 'No items expire within 7 days.');
      case _Filter.expired:
        return const EmptyState(icon: Icons.check_circle_outline_rounded, title: 'No expired items', message: 'Great job!');
      case _Filter.missing:
        return const EmptyState(
            icon: Icons.inventory_2_outlined, title: 'You have them all', message: 'Every supported vegetable is in stock.');
    }
  }
}

class _ItemCard extends StatelessWidget {
  final PantryItem item;
  const _ItemCard({required this.item});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return AppCard(
      onTap: () => showItemSheet(context, item),
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          IconBadge(emoji: item.emoji, size: 48),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(child: Text(item.name, style: t.titleSmall, maxLines: 1, overflow: TextOverflow.ellipsis)),
                    if (item.inStock) ...[
                      const SizedBox(width: 8),
                      Flexible(
                        child: Text(item.displayQuantity,
                            style: t.labelMedium, maxLines: 1, overflow: TextOverflow.ellipsis, textAlign: TextAlign.end),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 6),
                Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    StatusPill.forItem(item),
                    if (item.inStock && item.storageMethod.isNotEmpty)
                      Text(item.storageMethod, style: t.labelSmall),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(width: 4),
          Icon(item.inStock ? Icons.chevron_right_rounded : Icons.add_circle_outline_rounded,
              color: AppTheme.textTertiaryColor),
        ],
      ),
    );
  }
}
