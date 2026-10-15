import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../models/pantry_item.dart';
import '../../services/pantry_provider.dart';
import '../../widgets/ui.dart';
import '../pantry/pantry_sheets.dart';

/// In-app expiry alerts computed from the user's pantry.
class NotificationsScreen extends StatelessWidget {
  const NotificationsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final pantry = context.watch<PantryProvider>();
    final expired = pantry.expired, soon = pantry.expiringSoon;
    return Scaffold(
      appBar: AppBar(title: const Text('Expiry alerts')),
      body: RefreshIndicator(
        onRefresh: pantry.load,
        child: ListView(
          padding: EdgeInsets.only(bottom: 32 + MediaQuery.paddingOf(context).bottom),
          children: [
            ContentWidth(
              maxWidth: 680,
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                if (pantry.error != null) ...[
                  const SizedBox(height: 8),
                  ErrorState(message: pantry.error!, onRetry: pantry.load, compact: true),
                ],
                if (!pantry.hasLoaded && pantry.isLoading)
                  const LoadingView()
                else if (expired.isEmpty && soon.isEmpty)
                  const EmptyState(
                    icon: Icons.notifications_none_rounded,
                    title: 'No alerts',
                    message: 'Nothing in your pantry expires in the next 7 days.',
                  )
                else ...[
                  if (expired.isNotEmpty) ...[
                    const SectionTitle('Expired'),
                    for (final i in expired) _tile(context, i),
                  ],
                  if (soon.isNotEmpty) ...[
                    const SectionTitle('Expiring within 7 days'),
                    for (final i in soon) _tile(context, i),
                  ],
                ],
              ]),
            ),
          ],
        ),
      ),
    );
  }

  Widget _tile(BuildContext context, PantryItem item) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: AppCard(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          onTap: () => showItemSheet(context, item),
          child: Row(children: [
            IconBadge(emoji: item.emoji, size: 40),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(item.name, style: Theme.of(context).textTheme.titleSmall, maxLines: 1, overflow: TextOverflow.ellipsis),
                Text(item.displayQuantity,
                    style: Theme.of(context).textTheme.bodySmall, maxLines: 1, overflow: TextOverflow.ellipsis),
                const SizedBox(height: 4),
                StatusPill.forItem(item),
              ]),
            ),
          ]),
        ),
      );
}
