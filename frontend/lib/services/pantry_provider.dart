import 'package:flutter/foundation.dart';

import '../models/pantry_item.dart';
import 'api_client.dart';
import 'api_service.dart';

/// Pantry state for the signed-in user. Created per session (see main.dart),
/// so a new account never sees the previous account's items.
///
/// The UI is only updated from server responses: if a save fails, the error
/// is reported and nothing is shown as saved.
class PantryProvider extends ChangeNotifier {
  List<PantryItem> _items = const [];
  bool _isLoading = false;
  bool _loadedOnce = false;
  String? _error;
  bool _isSaving = false;

  List<PantryItem> get items => _items;
  bool get isLoading => _isLoading;
  bool get hasLoaded => _loadedOnce;
  bool get isSaving => _isSaving;
  String? get error => _error;

  List<PantryItem> get inStock => _items.where((i) => i.inStock).toList();
  List<PantryItem> get notInStock => _items.where((i) => !i.inStock && i.isCatalog).toList();
  List<PantryItem> get expiringSoon =>
      inStock.where((i) => i.isExpiringSoon).toList()..sort(_byExpiry);
  List<PantryItem> get expired => inStock.where((i) => i.isExpired).toList()..sort(_byExpiry);

  /// Items needing attention, soonest first.
  List<PantryItem> get attention => [...expired, ...expiringSoon];

  static int _byExpiry(PantryItem a, PantryItem b) =>
      (a.earliestExpiry ?? DateTime(9999)).compareTo(b.earliestExpiry ?? DateTime(9999));

  PantryItem? byId(String id) {
    for (final i in _items) {
      if (i.id == id) return i;
    }
    return null;
  }

  Future<void> load() async {
    if (_isLoading) return;
    _isLoading = true;
    _error = null;
    notifyListeners();
    try {
      _items = await ApiService.getPantry();
      _loadedOnce = true;
    } on ApiException catch (e) {
      _error = e.message;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<T> _write<T>(Future<T> Function() op) async {
    _isSaving = true;
    notifyListeners();
    try {
      return await op();
    } finally {
      _isSaving = false;
      notifyListeners();
    }
  }

  /// Adds items; [idempotencyKey] must stay the same if the user retries the
  /// same submission so the server never stores it twice.
  Future<void> addItems(List<Map<String, dynamic>> items, {required String idempotencyKey, String source = 'manual'}) =>
      _write(() async {
        _items = await ApiService.addPantryItems(items, idempotencyKey: idempotencyKey, source: source);
        _loadedOnce = true;
      });

  Future<void> updateItem(String id, {required double quantity, required String unit, DateTime? expiry}) =>
      _write(() async {
        await ApiService.updatePantryItem(id, quantity: quantity, unit: unit, expiry: expiry);
        _items = await ApiService.getPantry();
      });

  Future<void> deleteItem(String id) => _write(() async {
        await ApiService.deletePantryItem(id);
        _items = await ApiService.getPantry();
      });

  Future<void> consume(String id, double quantity, String unit) => _write(() async {
        await ApiService.consume(id, quantity, unit);
        _items = await ApiService.getPantry();
      });

  Future<void> refreshExpiry() => _write(() async {
        _items = await ApiService.refreshExpiry();
      });
}
