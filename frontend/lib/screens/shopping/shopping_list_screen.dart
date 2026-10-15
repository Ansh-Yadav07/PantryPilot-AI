import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../services/api_client.dart';
import '../../services/shopping_provider.dart';
import '../../theme/app_theme.dart';
import '../../widgets/ui.dart';

class ShoppingListScreen extends StatefulWidget {
  const ShoppingListScreen({super.key});

  @override
  State<ShoppingListScreen> createState() => _ShoppingListScreenState();
}

class _ShoppingListScreenState extends State<ShoppingListScreen> {
  final _name = TextEditingController();
  final _focus = FocusNode();
  bool _adding = false;

  @override
  void dispose() {
    _name.dispose();
    _focus.dispose();
    super.dispose();
  }

  Future<void> _guard(Future<void> Function() op) async {
    try {
      await op();
    } on ApiException catch (e) {
      if (mounted) showAppSnack(context, e.message, error: true);
    }
  }

  Future<void> _add([String? preset]) async {
    final name = (preset ?? _name.text).trim();
    if (name.isEmpty || _adding) return;
    setState(() => _adding = true);
    await _guard(() async {
      await context.read<ShoppingProvider>().add(name, source: preset != null ? 'suggestion' : 'manual');
      if (preset == null) _name.clear();
    });
    if (mounted) setState(() => _adding = false);
  }

  @override
  Widget build(BuildContext context) {
    final shop = context.watch<ShoppingProvider>();
    final t = Theme.of(context).textTheme;
    final open = shop.open, done = shop.done;

    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: shop.load,
          child: ListView(
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            padding: EdgeInsets.only(bottom: 32 + MediaQuery.paddingOf(context).bottom),
            children: [
              ContentWidth(
                maxWidth: 760,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    PageHeader(
                      title: 'Shopping list',
                      subtitle: shop.items.isEmpty ? 'Plan your next grocery run' : '${open.length} to buy · ${done.length} done',
                    ),
                    Row(children: [
                      Expanded(
                        child: TextField(
                          controller: _name,
                          focusNode: _focus,
                          enabled: !_adding,
                          textCapitalization: TextCapitalization.sentences,
                          textInputAction: TextInputAction.done,
                          onSubmitted: (_) => _add(),
                          decoration: const InputDecoration(hintText: 'Add an item, e.g. Milk', prefixIcon: Icon(Icons.add_rounded)),
                        ),
                      ),
                      const SizedBox(width: 8),
                      SizedBox(
                        height: 52,
                        child: FilledButton(
                          onPressed: _adding ? null : () => _add(),
                          child: _adding
                              ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                              : const Text('Add'),
                        ),
                      ),
                    ]),
                    if (shop.error != null) ...[
                      const SizedBox(height: 12),
                      ErrorState(message: shop.error!, onRetry: shop.load, compact: true),
                    ],
                    if (shop.suggestions.isNotEmpty) ...[
                      const SectionTitle('Suggested from your pantry'),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          for (final s in shop.suggestions)
                            ActionChip(
                              avatar: s.emoji != null ? Text(s.emoji!, textScaler: TextScaler.noScaling) : const Icon(Icons.add, size: 18),
                              label: Text('${s.name} · ${s.reason.toLowerCase()}'),
                              onPressed: _adding ? null : () => _add(s.name),
                            ),
                        ],
                      ),
                    ],
                    const SectionTitle('To buy'),
                    if (!shop.hasLoaded && shop.isLoading)
                      const LoadingView()
                    else if (open.isEmpty)
                      AppCard(
                        child: EmptyState(
                          icon: Icons.shopping_cart_outlined,
                          title: done.isEmpty ? 'Your list is empty' : 'All done!',
                          message: done.isEmpty
                              ? 'Add items above, or add missing ingredients from a recipe.'
                              : 'Everything on your list has been picked up.',
                        ),
                      )
                    else
                      _list(open, shop),
                    if (done.isNotEmpty) ...[
                      SectionTitle('Done', actionLabel: 'Clear done', onAction: () => _guard(shop.clearChecked)),
                      _list(done, shop),
                    ],
                    const SizedBox(height: 8),
                    Text('Your list is saved to your account.', style: t.bodySmall, textAlign: TextAlign.center),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _list(List<ShoppingItem> items, ShoppingProvider shop) {
    return AppCard(
      padding: EdgeInsets.zero,
      child: Column(children: [
        for (var i = 0; i < items.length; i++) ...[
          if (i > 0) const Divider(indent: 56),
          _tile(items[i], shop),
        ],
      ]),
    );
  }

  Widget _tile(ShoppingItem item, ShoppingProvider shop) {
    final busy = shop.isBusy(item.id);
    return Dismissible(
      key: ValueKey(item.id),
      direction: DismissDirection.endToStart,
      background: Container(
        color: AppTheme.dangerLight,
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20),
        child: const Icon(Icons.delete_outline_rounded, color: AppTheme.dangerColor),
      ),
      confirmDismiss: (_) async {
        try {
          await shop.remove(item);
          return true;
        } on ApiException catch (e) {
          if (mounted) showAppSnack(context, e.message, error: true);
          return false;
        }
      },
      child: CheckboxListTile(
        controlAffinity: ListTileControlAffinity.leading,
        value: item.checked,
        onChanged: busy ? null : (_) => _guard(() => shop.toggle(item)),
        title: Text(
          '${item.emoji != null ? '${item.emoji} ' : ''}${item.name}',
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            decoration: item.checked ? TextDecoration.lineThrough : null,
            color: item.checked ? AppTheme.textTertiaryColor : AppTheme.textPrimaryColor,
          ),
        ),
        subtitle: item.quantity.isNotEmpty ? Text(item.quantity) : null,
        secondary: busy
            ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
            : IconButton(
                tooltip: 'Remove ${item.name}',
                icon: const Icon(Icons.close_rounded, size: 20),
                onPressed: () => _guard(() => shop.remove(item)),
              ),
      ),
    );
  }
}
