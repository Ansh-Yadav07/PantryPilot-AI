import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Resolves the backend base URL (always ending in `/api`).
///
/// Priority:
///  1. A URL the user saved under "Server settings" (lets an installed APK be
///     pointed at a newly deployed backend without rebuilding).
///  2. The URL compiled in with `--dart-define=API_URL=https://host/api`.
///  3. Debug builds only: a local development server.
///
/// Release builds never fall back to localhost and only accept HTTPS.
class AppConfig {
  AppConfig._();

  static const String compiledApiUrl = String.fromEnvironment('API_URL');
  static const String _overrideKey = 'api_base_url_override';

  static String? _override;

  static Future<void> load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getString(_overrideKey);
      _override = (saved != null && validate(saved) == null) ? normalize(saved) : null;
    } catch (_) {
      _override = null;
    }
  }

  static String get apiBaseUrl {
    if (_override != null && _override!.isNotEmpty) return _override!;
    if (compiledApiUrl.isNotEmpty) return normalize(compiledApiUrl);
    return kDebugMode ? _debugDefault : '';
  }

  static bool get isConfigured => apiBaseUrl.isNotEmpty;
  static bool get usingOverride => _override != null;

  static String get _debugDefault {
    if (kIsWeb) return 'http://localhost:8000/api';
    // The Android emulator reaches the host machine via 10.0.2.2. A physical
    // phone needs a real URL (Server settings or --dart-define=API_URL).
    if (defaultTargetPlatform == TargetPlatform.android) return 'http://10.0.2.2:8000/api';
    return 'http://127.0.0.1:8000/api';
  }

  /// Accepts "https://host", "https://host/" or "https://host/api".
  static String normalize(String url) {
    var u = url.trim();
    while (u.endsWith('/')) {
      u = u.substring(0, u.length - 1);
    }
    if (!u.endsWith('/api')) u = '$u/api';
    return u;
  }

  /// Returns an error message, or null when the URL is acceptable.
  static String? validate(String url) {
    final uri = Uri.tryParse(url.trim());
    if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
      return 'Enter a full URL, e.g. https://your-api.onrender.com';
    }
    if (uri.scheme != 'https' && !(kDebugMode && uri.scheme == 'http')) {
      return 'The server address must start with https://';
    }
    return null;
  }

  static Future<void> setOverride(String? url) async {
    final prefs = await SharedPreferences.getInstance();
    if (url == null || url.trim().isEmpty) {
      await prefs.remove(_overrideKey);
      _override = null;
    } else {
      _override = normalize(url);
      await prefs.setString(_overrideKey, _override!);
    }
  }
}
