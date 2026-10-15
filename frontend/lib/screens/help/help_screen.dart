import 'package:flutter/material.dart';

import '../../widgets/ui.dart';

class HelpScreen extends StatelessWidget {
  const HelpScreen({super.key});

  static const _steps = [
    (Icons.center_focus_strong_rounded, 'Scan your vegetables',
        'Take a photo and PantryPilot identifies 22 common vegetables right on your phone. Review the results, then save them.'),
    (Icons.receipt_long_rounded, 'Scan receipts',
        'Photograph a grocery receipt to add items and record the bill. You check every value before anything is saved.'),
    (Icons.schedule_rounded, 'Watch expiry dates',
        'Items are sorted by how soon they expire. Expiry dates you don\'t enter are estimated and labelled as estimates.'),
    (Icons.restaurant_menu_rounded, 'Cook what you have',
        'Recipe ideas and meal plans are generated from your pantry, using soon-to-expire items first.'),
  ];

  static const _faq = [
    ('Does the vegetable scanner need internet?',
        'No. The detection model runs on your device. Saving the results to your pantry needs a connection.'),
    ('Which features need internet?',
        'Your pantry, shopping list, expenses and meal plans are stored in your account, and receipts, recipes and insights use an AI service on our server.'),
    ('How accurate is the scanner?',
        'It works best with clear, well-lit photos of the 22 supported vegetables. Low-confidence results are flagged and left unticked so you can check them.'),
    ('How is waste risk calculated?',
        'It is rule-based: items expiring within 3 days are high risk, and expired items are critical.'),
    ('Is my data private?',
        'Each account only sees its own data. Your password is stored hashed, and your sign-in token is kept in your phone\'s secure storage.'),
  ];

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Help & support')),
      body: ListView(
        padding: EdgeInsets.only(bottom: 32 + MediaQuery.paddingOf(context).bottom),
        children: [
          ContentWidth(
            maxWidth: 760,
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              const SectionTitle('Getting started'),
              for (final s in _steps)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: AppCard(
                    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      IconBadge(icon: s.$1, size: 40),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(s.$2, style: t.titleSmall),
                          const SizedBox(height: 4),
                          Text(s.$3, style: t.bodyMedium),
                        ]),
                      ),
                    ]),
                  ),
                ),
              const SectionTitle('Frequently asked questions'),
              AppCard(
                padding: EdgeInsets.zero,
                child: Column(children: [
                  for (final q in _faq)
                    ExpansionTile(
                      title: Text(q.$1, style: t.titleSmall),
                      shape: const Border(),
                      childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                      expandedCrossAxisAlignment: CrossAxisAlignment.start,
                      children: [Text(q.$2, style: t.bodyMedium)],
                    ),
                ]),
              ),
            ]),
          ),
        ],
      ),
    );
  }
}
