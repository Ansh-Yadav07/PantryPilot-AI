import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../main.dart';
import '../../models/pantry_item.dart';
import '../../services/api_client.dart';
import '../../services/api_service.dart';
import '../../services/auth_provider.dart';
import '../../services/pantry_provider.dart';
import '../../services/shopping_provider.dart';
import '../../theme/app_theme.dart';
import '../../widgets/ui.dart';
import '../pantry/ingredient_scanner_screen.dart';
import '../pantry/pantry_sheets.dart';
import '../receipt/receipt_scanner_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  Map<String, dynamic>? _analytics;
  String? _analyticsError;

  @override
  void initState() {
    super.initState();
    _loadAnalytics();
  }

  Future<void> _loadAnalytics() async {
    try {
      final a = await ApiService.getAnalytics();
      if (!mounted) return;
      setState(() {
        _analytics = a;
        _analyticsError = null;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _analyticsError = e.message);
    }
  }

  Future<void> _refresh() async {
    await Future.wait([
      context.read<PantryProvider>().load(),
      context.read<ShoppingProvider>().load(),
      _loadAnalytics(),
    ]);
  }

  String _greeting() {
    final h = DateTime.now().hour;
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final pantry = context.watch<PantryProvider>();
    final shopping = context.watch<ShoppingProvider>();
    final firstName = auth.displayName.split(' ').first;
    final attention = pantry.attention;

    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            padding: EdgeInsets.only(bottom: 32 + MediaQuery.paddingOf(context).bottom),
            children: [
              ContentWidth(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    PageHeader(
                      title: '${_greeting()}${firstName.isNotEmpty ? ', $firstName' : ''}',
                      subtitle: "Here's what's happening in your kitchen",
                      actions: [
                        IconButton(
                          tooltip: 'Expiry alerts',
                          onPressed: () => openNotifications(context),
                          icon: Badge(
                            isLabelVisible: attention.isNotEmpty,
                            label: Text('${attention.length}'),
                            child: const Icon(Icons.notifications_none_rounded),
                          ),
                        ),
                      ],
                    ),
                    if (pantry.error != null && !pantry.hasLoaded)
                      ErrorState(message: pantry.error!, onRetry: pantry.load, compact: true),
                    _QuickActions(),
                    const SectionTitle('Overview'),
                    if (!pantry.hasLoaded && pantry.isLoading)
                      const LoadingView()
                    else
                      ResponsiveGrid(
                        minItemWidth: 150,
                        children: [
                          StatTile(
                            icon: Icons.kitchen_rounded,
                            label: 'Items in pantry',
                            value: '${pantry.inStock.length}',
                            onTap: () => openSection(context, AppSection.pantry),
                          ),
                          StatTile(
                            icon: Icons.schedule_rounded,
                            label: 'Expiring within 7 days',
                            value: '${pantry.expiringSoon.length}',
                            color: AppTheme.warningColor,
                            onTap: () => openNotifications(context),
                          ),
                          StatTile(
                            icon: Icons.delete_outline_rounded,
                            label: 'Expired — at risk of waste',
                            value: '${pantry.expired.length}',
                            color: AppTheme.dangerColor,
                            onTap: () => openNotifications(context),
                          ),
                          StatTile(
                            icon: Icons.shopping_cart_rounded,
                            label: 'On your shopping list',
                            value: '${shopping.open.length}',
                            color: AppTheme.infoColor,
                            onTap: () => openSection(context, AppSection.shopping),
                          ),
                        ],
                      ),
                    SectionTitle(
                      'Use these first',
                      actionLabel: attention.isEmpty ? null : 'View pantry',
                      onAction: () => openSection(context, AppSection.pantry),
                    ),
                    if (pantry.hasLoaded) _AttentionList(items: attention.take(5).toList(), hasStock: pantry.inStock.isNotEmpty),
                    if (attention.isNotEmpty) ...[
                      const SizedBox(height: 12),
                      _CookCard(names: attention.where((i) => !i.isExpired).take(3).map((i) => i.name).toList()),
                    ],
                    const SectionTitle('This month'),
                    LayoutBuilder(builder: (context, c) {
                      final spend = _SpendCard(analytics: _analytics, error: _analyticsError, onRetry: _loadAnalytics);
                      final list = _ShoppingProgress(shopping: shopping);
                      if (c.maxWidth < 640) return Column(children: [spend, const SizedBox(height: 12), list]);
                      return IntrinsicHeight(
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [Expanded(child: spend), const SizedBox(width: 12), Expanded(child: list)],
                        ),
                      );
                    }),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _QuickActions extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    Widget action(IconData icon, String label, String hint, Color color, VoidCallback onTap) => AppCard(
          onTap: onTap,
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              IconBadge(icon: icon, color: color, size: 40),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label, style: Theme.of(context).textTheme.titleSmall, maxLines: 2, overflow: TextOverflow.ellipsis),
                    const SizedBox(height: 2),
                    Text(hint, style: Theme.of(context).textTheme.bodySmall, maxLines: 2, overflow: TextOverflow.ellipsis),
                  ],
                ),
              ),
            ],
          ),
        );

    return ResponsiveGrid(
      minItemWidth: 260,
      spacing: 10,
      children: [
        action(Icons.center_focus_strong_rounded, 'Scan vegetables', 'Identified on your phone', AppTheme.primaryColor,
            () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const IngredientScannerScreen()))),
        action(Icons.receipt_long_rounded, 'Scan a receipt', 'Add groceries and the bill', AppTheme.accentColor,
            () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const ReceiptScannerScreen()))),
        action(Icons.add_rounded, 'Add an item', 'Enter it yourself', AppTheme.infoColor, () => showAddItemSheet(context)),
      ],
    );
  }
}

class _AttentionList extends StatelessWidget {
  final List<PantryItem> items;
  final bool hasStock;
  const _AttentionList({required this.items, required this.hasStock});

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return AppCard(
        child: hasStock
            ? const EmptyState(
                icon: Icons.check_circle_outline_rounded,
                title: 'Everything is fresh',
                message: 'Nothing in your pantry expires in the next week.',
              )
            : EmptyState(
                icon: Icons.kitchen_outlined,
                title: 'Your pantry is empty',
                message: 'Scan vegetables or a receipt, or add items yourself, to start tracking freshness.',
                actionLabel: 'Add an item',
                onAction: () => showAddItemSheet(context),
              ),
      );
    }
    return AppCard(
      padding: EdgeInsets.zero,
      child: Column(
        children: [
          for (var i = 0; i < items.length; i++) ...[
            if (i > 0) const Divider(indent: 16, endIndent: 16),
            InkWell(
              onTap: () => showItemSheet(context, items[i]),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                child: Row(
                  children: [
                    IconBadge(emoji: items[i].emoji, size: 40),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(items[i].name,
                              style: Theme.of(context).textTheme.titleSmall, maxLines: 1, overflow: TextOverflow.ellipsis),
                          const SizedBox(height: 2),
                          Text(items[i].displayQuantity,
                              style: Theme.of(context).textTheme.bodySmall, maxLines: 1, overflow: TextOverflow.ellipsis),
                          const SizedBox(height: 6),
                          StatusPill.forItem(items[i]),
                        ],
                      ),
                    ),
                    const Icon(Icons.chevron_right_rounded, color: AppTheme.textTertiaryColor),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _CookCard extends StatelessWidget {
  final List<String> names;
  const _CookCard({required this.names});

  @override
  Widget build(BuildContext context) {
    if (names.isEmpty) return const SizedBox.shrink();
    return AppCard(
      color: AppTheme.lightGreen,
      borderColor: AppTheme.lightGreen,
      onTap: () => openSection(context, AppSection.recipes),
      child: Row(
        children: [
          const IconBadge(icon: Icons.restaurant_menu_rounded, color: AppTheme.primaryDark, size: 44),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Cook before it spoils', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 2),
                Text('Get recipe ideas using ${names.join(', ')}.',
                    style: Theme.of(context).textTheme.bodySmall, maxLines: 2, overflow: TextOverflow.ellipsis),
              ],
            ),
          ),
          const Icon(Icons.chevron_right_rounded, color: AppTheme.primaryDark),
        ],
      ),
    );
  }
}

class _SpendCard extends StatelessWidget {
  final Map<String, dynamic>? analytics;
  final String? error;
  final VoidCallback onRetry;
  const _SpendCard({required this.analytics, required this.error, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    Widget body;
    if (analytics == null && error != null) {
      body = Row(children: [
        Expanded(child: Text(error!, style: t.bodySmall)),
        TextButton(onPressed: onRetry, child: const Text('Retry')),
      ]);
    } else if (analytics == null) {
      body = const Padding(padding: EdgeInsets.all(8), child: LinearProgressIndicator());
    } else {
      final spend = (analytics!['monthly_spend_raw'] as num?) ?? 0;
      body = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(formatMoney(spend), style: t.headlineSmall),
          const SizedBox(height: 2),
          Text('${analytics!['spend_comparison'] ?? ''}', style: t.bodySmall),
        ],
      );
    }
    return AppCard(
      onTap: () => openSection(context, AppSection.insights),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.payments_outlined, size: 20, color: AppTheme.accentColor),
            const SizedBox(width: 8),
            Expanded(child: Text('Grocery spending', style: t.titleSmall)),
            const Icon(Icons.chevron_right_rounded, color: AppTheme.textTertiaryColor),
          ]),
          const SizedBox(height: 12),
          body,
        ],
      ),
    );
  }
}

class _ShoppingProgress extends StatelessWidget {
  final ShoppingProvider shopping;
  const _ShoppingProgress({required this.shopping});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final total = shopping.items.length;
    final done = shopping.done.length;
    return AppCard(
      onTap: () => openSection(context, AppSection.shopping),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.checklist_rounded, size: 20, color: AppTheme.infoColor),
            const SizedBox(width: 8),
            Expanded(child: Text('Shopping list', style: t.titleSmall)),
            const Icon(Icons.chevron_right_rounded, color: AppTheme.textTertiaryColor),
          ]),
          const SizedBox(height: 12),
          if (total == 0)
            Text(shopping.suggestions.isEmpty ? 'Your list is empty.' : '${shopping.suggestions.length} suggested to restock',
                style: t.bodyMedium)
          else ...[
            Text('$done of $total picked up', style: t.titleMedium),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: LinearProgressIndicator(
                value: total == 0 ? 0 : done / total,
                minHeight: 8,
                backgroundColor: AppTheme.surfaceMuted,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
