import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../config/app_config.dart';

/// Error surfaced to the UI. [message] is always safe to show to the user.
class ApiException implements Exception {
  final int? statusCode;
  final String message;
  const ApiException(this.message, {this.statusCode});

  bool get isUnauthorized => statusCode == 401;
  bool get isNetwork => statusCode == null;

  @override
  String toString() => message;
}

/// Single HTTP client used by every feature: one base URL, auth header,
/// timeouts, JSON decoding, error mapping, and safe retries.
///
/// Only idempotent GET requests are retried automatically. POST/PATCH/DELETE
/// are never retried blindly; writes that may be repeated by the user carry an
/// idempotency key instead.
class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  http.Client _http = http.Client();
  String? _token;

  /// Called when an authenticated request is rejected with 401.
  VoidCallback? onUnauthorized;

  @visibleForTesting
  set httpClient(http.Client client) => _http = client;

  void setToken(String? token) => _token = token;
  bool get hasToken => _token != null && _token!.isNotEmpty;

  static const _defaultTimeout = Duration(seconds: 30);

  DateTime? _awakeUntil;

  /// Free cloud hosting tiers put idle servers to sleep and take up to a
  /// minute to wake. Ping the health endpoint with a long timeout first so the
  /// real request doesn't time out. Never throws.
  Future<void> ensureAwake() async {
    if (_awakeUntil != null && DateTime.now().isBefore(_awakeUntil!)) return;
    try {
      await _send(() => _http.get(_uri('/health'), headers: _headers(json: false)), const Duration(seconds: 75));
      _awakeUntil = DateTime.now().add(const Duration(minutes: 5));
    } catch (_) {
      // The real request will surface a proper error.
    }
  }

  Uri _uri(String path, [Map<String, String>? query]) {
    final base = AppConfig.apiBaseUrl;
    if (base.isEmpty) {
      throw const ApiException('The server address is not configured. Open Server settings on the sign-in screen.');
    }
    return Uri.parse('$base$path').replace(queryParameters: query);
  }

  Map<String, String> _headers({bool json = true}) => {
        if (json) 'Content-Type': 'application/json',
        'Accept': 'application/json',
        if (hasToken) 'Authorization': 'Bearer $_token',
      };

  Future<dynamic> get(String path, {Map<String, String>? query, Duration? timeout, int retries = 2}) async {
    var attempt = 0;
    while (true) {
      try {
        return await _send(() => _http.get(_uri(path, query), headers: _headers(json: false)), timeout);
      } on ApiException catch (e) {
        final retriable = e.isNetwork || e.statusCode == 502 || e.statusCode == 503 || e.statusCode == 504;
        if (!retriable || attempt >= retries) rethrow;
        attempt++;
        await Future.delayed(Duration(milliseconds: 400 * pow(3, attempt - 1).toInt()));
      }
    }
  }

  Future<dynamic> post(String path, {Object? body, Duration? timeout}) =>
      _send(() => _http.post(_uri(path), headers: _headers(), body: jsonEncode(body ?? {})), timeout);

  Future<dynamic> patch(String path, {Object? body, Duration? timeout}) =>
      _send(() => _http.patch(_uri(path), headers: _headers(), body: jsonEncode(body ?? {})), timeout);

  Future<dynamic> put(String path, {Object? body, Duration? timeout}) =>
      _send(() => _http.put(_uri(path), headers: _headers(), body: jsonEncode(body ?? {})), timeout);

  Future<dynamic> delete(String path, {Duration? timeout}) =>
      _send(() => _http.delete(_uri(path), headers: _headers(json: false)), timeout);

  Future<dynamic> postImage(String path, Uint8List bytes, {String filename = 'image.jpg', Duration? timeout}) {
    return _send(() async {
      final req = http.MultipartRequest('POST', _uri(path))
        ..headers.addAll(_headers(json: false))
        ..files.add(http.MultipartFile.fromBytes('file', bytes, filename: filename));
      return http.Response.fromStream(await _http.send(req));
    }, timeout);
  }

  Future<dynamic> _send(Future<http.Response> Function() request, Duration? timeout) async {
    final authed = hasToken;
    http.Response res;
    try {
      res = await request().timeout(timeout ?? _defaultTimeout);
    } on ApiException {
      rethrow;
    } on TimeoutException {
      throw const ApiException('The server took too long to respond. Please try again.');
    } on SocketException {
      throw const ApiException('No connection to the server. Check your internet connection and try again.');
    } on http.ClientException {
      throw const ApiException('Could not reach the server. Check your internet connection and try again.');
    } on HandshakeException {
      throw const ApiException('Secure connection to the server failed.');
    }

    dynamic body;
    if (res.body.isNotEmpty) {
      try {
        body = jsonDecode(utf8.decode(res.bodyBytes));
      } on FormatException {
        body = null;
      }
    }
    if (res.statusCode >= 200 && res.statusCode < 300) {
      if (res.body.isNotEmpty && body == null) {
        throw ApiException('The server sent an unexpected response.', statusCode: res.statusCode);
      }
      return body;
    }
    if (res.statusCode == 401 && authed) onUnauthorized?.call();
    throw ApiException(_errorMessage(res.statusCode, body), statusCode: res.statusCode);
  }

  static String _errorMessage(int status, dynamic body) {
    final detail = body is Map ? body['detail'] : null;
    if (detail is String && detail.isNotEmpty) return detail;
    if (detail is List && detail.isNotEmpty) {
      // FastAPI validation errors: [{loc: [...], msg: "..."}]
      final first = detail.first;
      if (first is Map && first['msg'] != null) {
        final field = (first['loc'] is List && (first['loc'] as List).isNotEmpty) ? (first['loc'] as List).last : null;
        final msg = first['msg'].toString().replaceFirst('Value error, ', '');
        return field is String && field != 'body' ? '${_humanField(field)}: $msg' : msg;
      }
    }
    switch (status) {
      case 401:
        return 'Your session has expired. Please sign in again.';
      case 404:
        return 'Not found.';
      case 413:
        return 'The file is too large.';
      case 429:
        return 'Too many requests. Please wait a moment and try again.';
      case 502:
      case 503:
      case 504:
        return 'The service is temporarily unavailable. Please try again shortly.';
      default:
        return 'Something went wrong (error $status). Please try again.';
    }
  }

  static String _humanField(String f) => f.replaceAll('_', ' ').replaceFirstMapped(RegExp(r'^.'), (m) => m[0]!.toUpperCase());
}

/// Random key used to make a write safe to retry (server de-duplicates it).
String newIdempotencyKey() {
  final r = Random.secure();
  return List.generate(16, (_) => r.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
}
