import 'dart:typed_data';

import '../models/pantry_item.dart';
import 'api_client.dart';

class AuthResult {
  final String token;
  final Map<String, dynamic> user;
  const AuthResult(this.token, this.user);

  factory AuthResult.fromJson(dynamic j) =>
      AuthResult(j['access_token'] as String, Map<String, dynamic>.from(j['user'] as Map));
}

/// Typed wrappers around every backend endpoint the app uses.
class ApiService {
  ApiService._();
  static ApiClient get _c => ApiClient.instance;

  static List<Map<String, dynamic>> _maps(dynamic list) =>
      (list as List? ?? const []).map((e) => Map<String, dynamic>.from(e as Map)).toList();

  // ── Health ────────────────────────────────────────────────────────────
  static Future<bool> ping() async {
    try {
      final r = await _c.get('/health', timeout: const Duration(seconds: 10), retries: 0);
      return r is Map && r['status'] == 'ok';
    } on ApiException {
      return false;
    }
  }

  // ── Auth ──────────────────────────────────────────────────────────────
  static Future<AuthResult> login(String email, String password) async =>
      AuthResult.fromJson(await _c.post('/auth/login', body: {'email': email, 'password': password}));

  static Future<AuthResult> register(String name, String email, String password) async => AuthResult.fromJson(
      await _c.post('/auth/register', body: {'name': name, 'email': email, 'password': password}));

  static Future<Map<String, dynamic>> me() async =>
      Map<String, dynamic>.from((await _c.get('/auth/me', retries: 1))['user'] as Map);

  static Future<Map<String, dynamic>> updateProfile(Map<String, dynamic> fields) async =>
      Map<String, dynamic>.from((await _c.patch('/auth/me', body: fields))['user'] as Map);

  static Future<AuthResult> changePassword(String current, String next) async => AuthResult.fromJson(
      await _c.post('/auth/change-password', body: {'current_password': current, 'new_password': next}));

  // ── Pantry ────────────────────────────────────────────────────────────
  static List<PantryItem> _pantry(dynamic list) {
    final maps = _maps(list);
    return maps.map((m) => PantryItem.fromJson(m)).toList();
  }

  static Future<List<PantryItem>> getPantry() async => _pantry(await _c.get('/pantry'));

  static Future<List<PantryItem>> addPantryItems(List<Map<String, dynamic>> items,
          {required String idempotencyKey, String source = 'manual'}) async =>
      _pantry(await _c.post('/pantry',
          body: {'items': items, 'idempotency_key': idempotencyKey, 'source': source},
          timeout: const Duration(seconds: 45)));

  static Future<void> updatePantryItem(String id, {required double quantity, required String unit, DateTime? expiry}) =>
      _c.patch('/pantry/${Uri.encodeComponent(id)}', body: {
        'quantity': quantity,
        'unit': unit,
        'expiry_date': expiry == null ? null : _date(expiry),
      });

  static Future<void> deletePantryItem(String id) => _c.delete('/pantry/${Uri.encodeComponent(id)}');

  static Future<void> consume(String id, double quantity, String unit) =>
      _c.post('/pantry/consume', body: {'ingredient_id': id, 'quantity': quantity, 'unit': unit});

  static Future<List<PantryItem>> refreshExpiry() async =>
      _pantry(await _c.post('/pantry/refresh-all-expiry', timeout: const Duration(seconds: 60)));

  // ── Receipts ──────────────────────────────────────────────────────────
  static Future<Map<String, dynamic>> processReceipt(Uint8List bytes, String filename) async =>
      Map<String, dynamic>.from(
          await _c.postImage('/receipt/process', bytes, filename: filename, timeout: const Duration(seconds: 90)));

  static Future<Map<String, dynamic>> confirmReceipt({
    required String idempotencyKey,
    required List<Map<String, dynamic>> items,
    Map<String, dynamic>? expense,
  }) async =>
      Map<String, dynamic>.from(await _c.post('/receipt/confirm',
          body: {'idempotency_key': idempotencyKey, 'items': items, if (expense != null) 'expense': expense},
          timeout: const Duration(seconds: 45)));

  // ── Recipes & meal plans ──────────────────────────────────────────────
  static Future<Map<String, dynamic>> recommendRecipes({
    List<String>? selectedIngredients,
    int servings = 2,
    int? maxCookingTime,
    List<String> dietaryPreferences = const [],
    List<String> excludeRecipes = const [],
  }) async =>
      Map<String, dynamic>.from(await _c.post('/recipes/recommend',
          body: {
            if (selectedIngredients != null && selectedIngredients.isNotEmpty) 'selected_ingredients': selectedIngredients,
            'servings': servings,
            if (maxCookingTime != null) 'max_cooking_time': maxCookingTime,
            'dietary_preferences': dietaryPreferences,
            if (excludeRecipes.isNotEmpty) 'exclude_recipes': excludeRecipes,
          },
          timeout: const Duration(seconds: 90)));

  static Future<Map<String, dynamic>> getMealPlan() async => Map<String, dynamic>.from(await _c.get('/meals/plan'));

  static Future<Map<String, dynamic>> generateMealPlan({int days = 7, List<String>? dietaryPreferences}) async =>
      Map<String, dynamic>.from(await _c.post('/meals/generate',
          body: {'days': days, if (dietaryPreferences != null) 'dietary_preferences': dietaryPreferences},
          timeout: const Duration(seconds: 120)));

  static Future<Map<String, dynamic>> updateMeal(
          {required String date, required String mealType, required String name}) async =>
      Map<String, dynamic>.from(
          await _c.put('/meals/update', body: {'date': date, 'meal_type': mealType, 'name': name}));

  static Future<void> resetMealPlan() => _c.delete('/meals/plan');

  // ── Expenses, analytics & insights ────────────────────────────────────
  static Future<Map<String, dynamic>> getExpenses({String? month}) async =>
      Map<String, dynamic>.from(await _c.get('/expenses', query: month == null ? null : {'month': month}));

  static Future<Map<String, dynamic>> addExpense(
          {required String title, required double amount, required String category, required DateTime date, String? notes}) async =>
      Map<String, dynamic>.from(await _c.post('/expenses', body: {
        'title': title,
        'amount': amount,
        'category': category,
        'date': _date(date),
        if (notes != null && notes.isNotEmpty) 'notes': notes,
      }));

  static Future<void> deleteExpense(String id) => _c.delete('/expenses/$id');

  static Future<Map<String, dynamic>> getAnalytics() async => Map<String, dynamic>.from(await _c.get('/analytics'));

  static Future<Map<String, dynamic>> getInsights() async =>
      Map<String, dynamic>.from(await _c.get('/ai/insights', timeout: const Duration(seconds: 45), retries: 0));

  // ── Shopping list ─────────────────────────────────────────────────────
  static Future<Map<String, dynamic>> getShopping() async => Map<String, dynamic>.from(await _c.get('/shopping'));

  static Future<Map<String, dynamic>> addShoppingItem(String name, {String? quantity, String source = 'manual'}) async =>
      Map<String, dynamic>.from(await _c.post('/shopping',
          body: {'name': name, if (quantity != null && quantity.isNotEmpty) 'quantity': quantity, 'source': source}));

  static Future<Map<String, dynamic>> updateShoppingItem(String id, Map<String, dynamic> fields) async =>
      Map<String, dynamic>.from(await _c.patch('/shopping/$id', body: fields));

  static Future<void> deleteShoppingItem(String id) => _c.delete('/shopping/$id');

  static Future<void> clearCheckedShopping() => _c.post('/shopping/clear-checked');

  static String _date(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
}
