import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:pantry_pilot_ai/main.dart';
import 'package:pantry_pilot_ai/services/api_client.dart';
import 'package:pantry_pilot_ai/services/auth_provider.dart';
import 'package:pantry_pilot_ai/services/session_store.dart';
import 'package:pantry_pilot_ai/theme/app_theme.dart';

const longName = 'Extra Long Organic Heirloom Cherry Tomatoes From The Farmers Market';

String _d(int days) {
  final d = DateTime.now().add(Duration(days: days));
  return DateTime(d.year, d.month, d.day).toIso8601String();
}

Map<String, dynamic> item(String id, String name,
    {bool inStock = true, int? days, String qty = '3 pcs', String emoji = '🥕', String status = 'fresh'}) => {
      'ingredient_id': id,
      'display_name': name,
      'category': 'Vegetables',
      'emoji': emoji,
      'image_asset': '$id.png',
      'in_stock': inStock,
      'total_quantity': inStock ? 3 : 0,
      'unit': 'pcs',
      'display_quantity': inStock ? qty : 'Not in pantry',
      'earliest_expiry': days == null ? null : _d(days),
      'expiry_display': days == null ? 'No expiry set' : 'In $days days',
      'expiry_status': status,
      'storage_method': 'refrigerator',
      'storage_tip': 'Keep in the crisper drawer away from ethylene-producing fruit.',
      'ai_predicted': true,
    };

List<Map<String, dynamic>> pantryFixture() => [
      item('tomato', longName, days: 1, status: 'expiring_soon', qty: '1250.5 g + 12 pcs'),
      item('carrot', 'Carrot', days: 12),
      item('potato', 'Potato', days: -3, status: 'expired', emoji: '🥔'),
      item('cabbage', 'Cabbage', days: 5, status: 'use_soon', emoji: '🥬'),
      item('lemon', 'Lemon', inStock: false, status: 'empty', emoji: '🍋'),
      {...item('paneer_extra_special', 'Homemade Malai Paneer With Extra Long Description', days: 2, status: 'expiring_soon'), 'image_asset': ''},
    ];

final user = {'id': '65f000000000000000000001', 'name': 'Priya Ramanathan Venkataraman', 'email': 'priya.ramanathan.venkataraman@example-long-domain.com', 'household_size': 4, 'created_at': '2026-01-05T10:00:00'};

http.Response jsonResponse(Object body, [int status = 200]) =>
    http.Response.bytes(utf8.encode(jsonEncode(body)), status, headers: {'content-type': 'application/json'});

/// Routes requests to fixture data. [overrides] can replace any response.
MockClient mockBackend({Map<String, http.Response Function(http.Request)> overrides = const {}}) {
  return MockClient((req) async {
    final key = '${req.method} ${req.url.path}';
    if (overrides.containsKey(key)) return overrides[key]!(req);
    switch (key) {
      case 'GET /api/auth/me':
        return jsonResponse({'user': user});
      case 'POST /api/auth/login':
      case 'POST /api/auth/register':
        return jsonResponse({'access_token': 'token-123', 'token_type': 'bearer', 'user': user});
      case 'GET /api/pantry':
        return jsonResponse(pantryFixture());
      case 'GET /api/shopping':
        return jsonResponse({
          'items': [
            {'id': 'a1', 'name': longName, 'quantity': '2 kg', 'category': 'Vegetables', 'checked': false},
            {'id': 'a2', 'name': 'Milk', 'quantity': '', 'category': 'Dairy', 'checked': true},
          ],
          'suggestions': [
            {'name': 'Potato', 'emoji': '🥔', 'reason': 'Expired'},
          ],
        });
      case 'GET /api/analytics':
        return jsonResponse({
          'monthly_spend_raw': 123456.75,
          'spend_comparison': '↑ 12.5% vs last month',
          'total_pantry_items': 5,
          'fresh_items_count': 1,
          'expiring_soon_count': 3,
          'expired_count': 1,
          'at_risk_items': [
            {'ingredient_id': 'tomato', 'name': longName, 'emoji': '🍅', 'risk_level': 'HIGH', 'expiry_display': 'Expires tomorrow'},
          ],
          'weekly_spending': [100, 0, 2500.5, 99999],
        });
      case 'GET /api/expenses':
        return jsonResponse({
          'total_this_month': 123456.75,
          'total_last_month': 99000,
          'expense_count': 2,
          'weekly_spending': [100, 0, 2500.5, 99999],
          'category_breakdown': [
            {'category': 'Snacks & Beverages and Other Extremely Long Category', 'amount': 100000, 'percentage': 81.0},
            {'category': 'Vegetables', 'amount': 23456.75, 'percentage': 19.0},
          ],
          'expenses': [
            {'id': 'e1', 'title': 'Big monthly shopping at the very large hypermarket downtown', 'amount': 100000, 'category': 'Groceries', 'date': '2026-10-10'},
          ],
        });
      case 'GET /api/meals/plan':
        return jsonResponse({
          'days': [
            for (var i = 0; i < 7; i++)
              {
                'date': '2026-10-${15 + i}',
                'day_short': 'Wed',
                'day_number': 15 + i,
                'is_today': i == 0,
                for (final m in ['breakfast', 'lunch', 'dinner'])
                  m: {
                    'name': 'Slow-cooked $longName curry with jeera rice',
                    'description': 'A hearty dish.',
                    'prep_time': '45 mins',
                    'calories': '650 kcal',
                    'ingredients_used': ['Tomato', 'Potato'],
                    'missing_ingredients': ['Cream'],
                    'uses_expiring_items': true,
                  },
              },
          ],
        });
      case 'GET /api/health':
        return jsonResponse({'status': 'ok'});
    }
    return jsonResponse({'detail': 'Not mocked: $key'}, 404);
  });
}

/// Builds a signed-in app around [child] with fixture data.
Future<AuthProvider> signedInAuth(MockClient client) async {
  ApiClient.instance.httpClient = client;
  final auth = AuthProvider(store: MemorySessionStore('token-123'), autoRestore: false);
  await auth.restoreSession();
  expect(auth.status, AuthStatus.authenticated);
  return auth;
}

Widget appShell(AuthProvider auth, Widget child) => ChangeNotifierProvider.value(
      value: auth,
      child: MaterialApp(theme: AppTheme.lightTheme, home: SessionScope(child: child)),
    );

Future<void> setSurface(WidgetTester tester, Size size, double textScale) async {
  tester.view.physicalSize = size * 2;
  tester.view.devicePixelRatio = 2;
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(() {
    tester.view.reset();
    tester.platformDispatcher.clearTextScaleFactorTestValue();
  });
}

/// Pumps enough frames for mocked futures to resolve without waiting on
/// infinite animations (progress indicators).
Future<void> settle(WidgetTester tester) async {
  for (var i = 0; i < 12; i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}
