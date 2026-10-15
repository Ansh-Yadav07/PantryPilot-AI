import 'package:flutter/foundation.dart';

import 'api_client.dart';
import 'api_service.dart';

class ShoppingItem {
  final String id;
  final String name;
  final String quantity;
  final String category;
  final String? emoji;
  final bool checked;

  const ShoppingItem(this.id, this.name, this.quantity, this.category, this.emoji, this.checked);

  factory ShoppingItem.fromJson(Map<String, dynamic> j) => ShoppingItem(
        j['id'].toString(),
        (j['name'] ?? '').toString(),
        (j['quantity'] ?? '').toString(),
        (j['category'] ?? 'Other').toString(),
        j['emoji']?.toString(),
        j['checked'] == true,
      );
}

class ShoppingSuggestion {
  final String name;
  final String? emoji;
  final String reason;
  const ShoppingSuggestion(this.name, this.emoji, this.reason);
}

/// Shopping list for the signed-in user, persisted on the server.
class ShoppingProvider extends ChangeNotifier {
  List<ShoppingItem> _items = const [];
  List<ShoppingSuggestion> _suggestions = const [];
  bool _isLoading = false;
  bool _loadedOnce = false;
  String? _error;
  final Set<String> _busy = {};

  List<ShoppingItem> get items => _items;
  List<ShoppingItem> get open => _items.where((i) => !i.checked).toList();
  List<ShoppingItem> get done => _items.where((i) => i.checked).toList();
  List<ShoppingSuggestion> get suggestions => _suggestions;
  bool get isLoading => _isLoading;
  bool get hasLoaded => _loadedOnce;
  String? get error => _error;
  bool isBusy(String id) => _busy.contains(id);

  Future<void> load() async {
    if (_isLoading) return;
    _isLoading = true;
    _error = null;
    notifyListeners();
    try {
      _apply(await ApiService.getShopping());
      _loadedOnce = true;
    } on ApiException catch (e) {
      _error = e.message;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  void _apply(Map<String, dynamic> data) {
    _items = (data['items'] as List? ?? [])
        .map((e) => ShoppingItem.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
    _suggestions = (data['suggestions'] as List? ?? [])
        .map((e) => ShoppingSuggestion((e['name'] ?? '').toString(), e['emoji']?.toString(), (e['reason'] ?? '').toString()))
        .toList();
  }

  Future<void> add(String name, {String? quantity, String source = 'manual'}) async {
    await ApiService.addShoppingItem(name, quantity: quantity, source: source);
    _apply(await ApiService.getShopping());
    notifyListeners();
  }

  Future<void> toggle(ShoppingItem item) => _mutate(item.id, () => ApiService.updateShoppingItem(item.id, {'checked': !item.checked}));

  Future<void> remove(ShoppingItem item) => _mutate(item.id, () => ApiService.deleteShoppingItem(item.id));

  Future<void> clearChecked() async {
    await ApiService.clearCheckedShopping();
    _apply(await ApiService.getShopping());
    notifyListeners();
  }

  Future<void> _mutate(String id, Future<void> Function() op) async {
    if (_busy.contains(id)) return;
    _busy.add(id);
    notifyListeners();
    try {
      await op();
      _apply(await ApiService.getShopping());
    } finally {
      _busy.remove(id);
      notifyListeners();
    }
  }
}
