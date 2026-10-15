/// A pantry entry as returned by GET /api/pantry: either one of the 22
/// catalog vegetables (possibly not in stock) or a custom item.
class PantryItem {
  final String id;
  final String name;
  final String category;
  final String emoji;
  final bool inStock;
  final double totalQuantity;
  final String unit;
  final String displayQuantity;
  final DateTime? earliestExpiry;
  final String expiryDisplay;

  /// fresh | use_soon | expiring_soon | expired | unknown | empty
  final String expiryStatus;
  final String storageMethod;
  final String storageTip;
  final bool aiPredicted;
  final bool isCatalog;

  const PantryItem({
    required this.id,
    required this.name,
    required this.category,
    required this.emoji,
    required this.inStock,
    required this.totalQuantity,
    required this.unit,
    required this.displayQuantity,
    required this.earliestExpiry,
    required this.expiryDisplay,
    required this.expiryStatus,
    required this.storageMethod,
    required this.storageTip,
    required this.aiPredicted,
    required this.isCatalog,
  });

  factory PantryItem.fromJson(Map<String, dynamic> j, {Set<String> catalogIds = const {}}) {
    final id = (j['ingredient_id'] ?? j['id'] ?? '').toString();
    return PantryItem(
      id: id,
      name: (j['display_name'] ?? j['name'] ?? id).toString(),
      category: (j['category'] ?? 'Other').toString(),
      emoji: (j['emoji'] ?? '📦').toString(),
      inStock: j['in_stock'] == true,
      totalQuantity: (j['total_quantity'] as num?)?.toDouble() ?? 0,
      unit: (j['unit'] ?? 'pcs').toString(),
      displayQuantity: (j['display_quantity'] ?? '').toString(),
      earliestExpiry: j['earliest_expiry'] != null ? DateTime.tryParse(j['earliest_expiry'].toString()) : null,
      expiryDisplay: (j['expiry_display'] ?? '').toString(),
      expiryStatus: (j['expiry_status'] ?? 'unknown').toString(),
      storageMethod: (j['storage_method'] ?? '').toString(),
      storageTip: (j['storage_tip'] ?? '').toString(),
      aiPredicted: j['ai_predicted'] == true,
      isCatalog: catalogIds.contains(id) || (j['image_asset'] ?? '').toString().isNotEmpty,
    );
  }

  bool get isExpired => expiryStatus == 'expired';
  bool get isExpiringSoon => expiryStatus == 'expiring_soon' || expiryStatus == 'use_soon';

  /// Days until expiry in the user's local calendar (negative when expired).
  int? get daysLeft {
    final e = earliestExpiry;
    if (e == null) return null;
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    return DateTime(e.year, e.month, e.day).difference(today).inDays;
  }
}
