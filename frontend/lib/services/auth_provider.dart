import 'package:flutter/foundation.dart';

import 'api_client.dart';
import 'api_service.dart';
import 'session_store.dart';

enum AuthStatus {
  /// Checking a stored session with the server (show splash, no private data).
  restoring,

  /// A stored session exists but the server could not be reached to verify it.
  offline,
  unauthenticated,
  authenticated,
}

class AuthProvider extends ChangeNotifier {
  final SessionStore _store;
  final ApiClient _client;

  AuthStatus _status = AuthStatus.restoring;
  Map<String, dynamic>? _user;
  bool _isSubmitting = false;
  String? _errorMessage;
  String? _notice;

  AuthProvider({SessionStore? store, ApiClient? client, bool autoRestore = true})
      : _store = store ?? SecureSessionStore(),
        _client = client ?? ApiClient.instance {
    _client.onUnauthorized = _handleSessionExpired;
    if (autoRestore) restoreSession();
  }

  AuthStatus get status => _status;
  bool get isAuthenticated => _status == AuthStatus.authenticated;
  bool get isSubmitting => _isSubmitting;
  Map<String, dynamic>? get user => _user;
  String get userId => (_user?['id'] ?? '').toString();
  String get displayName => (_user?['name'] ?? '').toString();
  String get email => (_user?['email'] ?? '').toString();
  String? get errorMessage => _errorMessage;

  /// One-off message for the sign-in screen (e.g. "session expired").
  String? takeNotice() {
    final n = _notice;
    _notice = null;
    return n;
  }

  Future<void> restoreSession() async {
    _status = AuthStatus.restoring;
    notifyListeners();
    final token = await _store.readToken();
    if (token == null || token.isEmpty) {
      _status = AuthStatus.unauthenticated;
      notifyListeners();
      return;
    }
    _client.setToken(token);
    try {
      await _client.ensureAwake();
      _user = await ApiService.me();
      _status = AuthStatus.authenticated;
    } on ApiException catch (e) {
      if (e.isUnauthorized || e.statusCode == 404) {
        await _clearSession();
        _notice = 'Your session has expired. Please sign in again.';
        _status = AuthStatus.unauthenticated;
      } else {
        // Can't verify right now; never show private data without verification.
        _errorMessage = e.message;
        _status = AuthStatus.offline;
      }
    }
    notifyListeners();
  }

  Future<bool> login(String email, String password) =>
      _authenticate(() => ApiService.login(email.trim().toLowerCase(), password));

  Future<bool> register(String name, String email, String password) =>
      _authenticate(() => ApiService.register(name.trim(), email.trim().toLowerCase(), password));

  Future<bool> _authenticate(Future<AuthResult> Function() call) async {
    if (_isSubmitting) return false; // ignore double taps
    _isSubmitting = true;
    _errorMessage = null;
    notifyListeners();
    try {
      await _client.ensureAwake();
      final result = await call();
      await _startSession(result);
      return true;
    } on ApiException catch (e) {
      _errorMessage = e.message;
      return false;
    } finally {
      _isSubmitting = false;
      notifyListeners();
    }
  }

  Future<void> _startSession(AuthResult result) async {
    _client.setToken(result.token);
    await _store.writeToken(result.token);
    _user = result.user;
    _status = AuthStatus.authenticated;
  }

  Future<void> updateProfile(Map<String, dynamic> fields) async {
    _user = await ApiService.updateProfile(fields);
    notifyListeners();
  }

  /// Changing the password invalidates every other session; this device
  /// receives a fresh token.
  Future<void> changePassword(String current, String next) async {
    final result = await ApiService.changePassword(current, next);
    await _startSession(result);
    notifyListeners();
  }

  Future<void> logout() async {
    await _clearSession();
    _status = AuthStatus.unauthenticated;
    notifyListeners();
  }

  void clearError() {
    if (_errorMessage != null) {
      _errorMessage = null;
      notifyListeners();
    }
  }

  void _handleSessionExpired() {
    if (_status != AuthStatus.authenticated) return;
    _clearSession();
    _notice = 'Your session has expired. Please sign in again.';
    _status = AuthStatus.unauthenticated;
    notifyListeners();
  }

  Future<void> _clearSession() async {
    _client.setToken(null);
    _user = null;
    await _store.clear();
  }
}
