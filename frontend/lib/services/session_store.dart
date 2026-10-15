import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Persists the auth token in platform secure storage
/// (Android Keystore-backed EncryptedSharedPreferences, iOS/macOS Keychain).
abstract class SessionStore {
  Future<String?> readToken();
  Future<void> writeToken(String token);
  Future<void> clear();
}

class SecureSessionStore implements SessionStore {
  static const _key = 'pp_auth_token';
  final FlutterSecureStorage _storage;

  SecureSessionStore()
      : _storage = const FlutterSecureStorage(
          aOptions: AndroidOptions(encryptedSharedPreferences: true),
          // Legacy (file-based) keychain works for unsigned local desktop builds.
          mOptions: MacOsOptions(useDataProtectionKeyChain: false),
        );

  @override
  Future<String?> readToken() async {
    try {
      return await _storage.read(key: _key);
    } catch (_) {
      // Corrupted keystore entry (e.g. after a backup restore): start fresh.
      await clear();
      return null;
    }
  }

  @override
  Future<void> writeToken(String token) => _storage.write(key: _key, value: token);

  @override
  Future<void> clear() async {
    try {
      await _storage.delete(key: _key);
    } catch (_) {}
  }
}

/// In-memory store for tests.
class MemorySessionStore implements SessionStore {
  String? token;
  MemorySessionStore([this.token]);
  @override
  Future<String?> readToken() async => token;
  @override
  Future<void> writeToken(String t) async => token = t;
  @override
  Future<void> clear() async => token = null;
}
