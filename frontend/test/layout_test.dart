import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pantry_pilot_ai/main.dart';
import 'package:pantry_pilot_ai/screens/auth/login_screen.dart';
import 'package:pantry_pilot_ai/screens/auth/register_screen.dart';
import 'package:pantry_pilot_ai/screens/dashboard/dashboard_screen.dart';
import 'package:pantry_pilot_ai/screens/help/help_screen.dart';
import 'package:pantry_pilot_ai/screens/meal_planner/meal_planner_screen.dart';
import 'package:pantry_pilot_ai/screens/notifications/notifications_screen.dart';
import 'package:pantry_pilot_ai/screens/pantry/pantry_screen.dart';
import 'package:pantry_pilot_ai/screens/pantry/ingredient_scanner_screen.dart';
import 'package:pantry_pilot_ai/screens/pantry/ingredient_results_screen.dart';
import 'package:pantry_pilot_ai/services/yolo_service.dart';
import 'package:image/image.dart' as img;
import 'package:pantry_pilot_ai/screens/profile/profile_screen.dart';
import 'package:pantry_pilot_ai/screens/receipt/receipt_confirmation_screen.dart';
import 'package:pantry_pilot_ai/screens/receipt/receipt_scanner_screen.dart';
import 'package:pantry_pilot_ai/screens/recipes/recipes_screen.dart';
import 'package:pantry_pilot_ai/screens/settings/settings_screen.dart';
import 'package:pantry_pilot_ai/screens/shopping/shopping_list_screen.dart';
import 'package:pantry_pilot_ai/screens/smart_dashboard/smart_dashboard_screen.dart';

import 'helpers.dart';

final receiptFixture = {
  'store_name': 'Sri Venkateshwara Fresh Fruits & Vegetables Super Market Pvt Ltd',
  'purchase_date': null,
  'total': null,
  'items_total': 412.5,
  'items': [
    {'name': longName, 'quantity': null, 'unit': null, 'price': 120.0, 'category': 'Vegetables', 'emoji': '🍅'},
    {'name': 'Dish soap', 'quantity': 1, 'unit': 'pcs', 'price': null, 'category': 'Household'},
  ],
};

final screens = <String, Widget Function()>{
  'shell': () => const ShellScreen(),
  'dashboard': () => const DashboardScreen(),
  'pantry': () => const PantryScreen(),
  'shopping': () => const ShoppingListScreen(),
  'recipes': () => const RecipesScreen(),
  'recipe detail': () => const RecipeDetailScreen(recipe: {
        'name': 'A very long recipe name that keeps going $longName',
        'description': 'Tasty.',
        'ingredients_used': [longName, 'Carrot'],
        'missing_ingredients': ['Coconut milk from a specialty store'],
        'prep_time': '45 min',
        'difficulty': 'Medium',
        'calories': '420 kcal',
        'servings': 4,
        'steps': ['Chop everything finely.', 'Cook gently for 30 minutes until soft.'],
      }),
  'insights': () => const SmartDashboardScreen(),
  'meal planner': () => const MealPlannerScreen(),
  'profile': () => const ProfileScreen(),
  'settings': () => const SettingsScreen(),
  'help': () => const HelpScreen(),
  'notifications': () => const NotificationsScreen(),
  'vegetable scanner': () => const IngredientScannerScreen(),
  'receipt scanner': () => const ReceiptScannerScreen(),
  'receipt review': () => ReceiptConfirmationScreen(receipt: receiptFixture),
  'detection review': () => IngredientResultsScreen(
        imageBytes: img.encodePng(img.Image(width: 64, height: 48)),
        result: const DetectionResult([
          Detection(1, 'tomato', 0.91, 2, 2, 30, 30),
          Detection(1, 'tomato', 0.85, 30, 10, 60, 40),
          Detection(19, 'snake_gourd', 0.31, 5, 20, 50, 46),
        ], 64, 48, Duration(milliseconds: 850)),
      ),
  'detection review (nothing found)': () => IngredientResultsScreen(
        imageBytes: img.encodePng(img.Image(width: 64, height: 48)),
        result: const DetectionResult([], 64, 48, Duration(milliseconds: 600)),
      ),
  'login': () => const LoginScreen(),
  'register': () => const RegisterScreen(),
};

void expectNoLayoutError(WidgetTester tester) {
  if (const bool.fromEnvironment("RAW_ERRORS")) return;
  final e = tester.takeException();
  if (e != null) fail(e is FlutterError ? e.toStringDeep() : '$e');
}

void main() {
  YoloService.labelsForTest = const ['cucumber', 'tomato', 'green_beans', 'lemon', 'eggplant', 'green_chilli', 'turnip',
      'coriander', 'pumpkin', 'potato', 'cauliflower', 'green_papaya', 'bitter_gourd', 'carrot', 'bottle_gourd',
      'capsicum', 'beetroot', 'cabbage', 'spring_onion', 'snake_gourd', 'radish', 'green_banana'];
  const sizes = {
    'small phone 320x568': Size(320, 568),
    'phone 360x800': Size(360, 800),
    'tablet 800x1280': Size(800, 1280),
    'desktop 1280x800': Size(1280, 800),
  };

  for (final screen in screens.entries) {
    for (final size in sizes.entries) {
      for (final scale in [1.0, 1.5, 2.0]) {
        if (size.value.width > 400 && scale > 1.5) continue;
        testWidgets('${screen.key} has no overflow on ${size.key} at ${scale}x text', (tester) async {
          await setSurface(tester, size.value, scale);
          final auth = await signedInAuth(mockBackend());
          await tester.pumpWidget(appShell(auth, screen.value()));
          await settle(tester);
          expectNoLayoutError(tester);
          // Scroll to the bottom to lay out everything below the fold.
          final scrollables = find.byType(Scrollable);
          if (scrollables.evaluate().isNotEmpty) {
            await tester.drag(scrollables.first, const Offset(0, -3000), warnIfMissed: false);
            await settle(tester);
          }
          expectNoLayoutError(tester);
        });
      }
    }
  }
}
