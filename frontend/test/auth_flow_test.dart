import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import 'package:pantry_pilot_ai/main.dart';
import 'package:pantry_pilot_ai/screens/auth/login_screen.dart';
import 'package:pantry_pilot_ai/services/api_client.dart';
import 'package:pantry_pilot_ai/services/auth_provider.dart';
import 'package:pantry_pilot_ai/services/session_store.dart';

import 'helpers.dart';

http.Response _err(int status, String detail) =>
    http.Response(jsonEncode({'detail': detail}), status, headers: {'content-type': 'application/json'});

Future<void> pumpApp(WidgetTester tester, AuthProvider auth) async {
  await tester.pumpWidget(ChangeNotifierProvider.value(value: auth, child: const PantryPilotApp()));
  await settle(tester);
}

void main() {
  testWidgets('empty and invalid fields show validation errors without calling the server', (tester) async {
    var calls = 0;
    ApiClient.instance.httpClient = mockBackend(overrides: {
      'POST /api/auth/login': (_) {
        calls++;
        return _err(401, 'nope');
      },
    });
    final auth = AuthProvider(store: MemorySessionStore(), autoRestore: false);
    await auth.restoreSession();
    await pumpApp(tester, auth);

    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await settle(tester);
    expect(find.text('Enter your email address'), findsOneWidget);
    expect(find.text('Enter your password'), findsOneWidget);

    await tester.enterText(find.byType(TextFormField).first, 'not-an-email');
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await settle(tester);
    expect(find.text('Enter a valid email address'), findsOneWidget);
    expect(calls, 0);
  });

  testWidgets('wrong password shows the server message and stays signed out', (tester) async {
    ApiClient.instance.httpClient =
        mockBackend(overrides: {'POST /api/auth/login': (_) => _err(401, 'Incorrect email or password.')});
    final store = MemorySessionStore();
    final auth = AuthProvider(store: store, autoRestore: false);
    await auth.restoreSession();
    await pumpApp(tester, auth);

    await tester.enterText(find.byType(TextFormField).at(0), 'a@b.com');
    await tester.enterText(find.byType(TextFormField).at(1), 'wrong-pass');
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await settle(tester);
    expect(find.text('Incorrect email or password.'), findsOneWidget);
    expect(auth.status, AuthStatus.unauthenticated);
    expect(store.token, isNull);
  });

  testWidgets('successful login stores the token, shows the app, and logout returns to sign-in', (tester) async {
    ApiClient.instance.httpClient = mockBackend();
    final store = MemorySessionStore();
    final auth = AuthProvider(store: store, autoRestore: false);
    await auth.restoreSession();
    await pumpApp(tester, auth);

    await tester.enterText(find.byType(TextFormField).at(0), 'Priya@Example.com ');
    await tester.enterText(find.byType(TextFormField).at(1), 'Passw0rd!');
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await settle(tester);

    expect(auth.status, AuthStatus.authenticated);
    expect(store.token, 'token-123');
    expect(find.byType(ShellScreen), findsOneWidget);
    expect(find.byType(LoginScreen), findsNothing);

    await auth.logout();
    await settle(tester);
    expect(store.token, isNull);
    expect(find.byType(LoginScreen), findsOneWidget);
    expect(find.byType(ShellScreen), findsNothing);
  });

  testWidgets('a stored token is verified with the server before showing private data', (tester) async {
    ApiClient.instance.httpClient =
        mockBackend(overrides: {'GET /api/auth/me': (_) => _err(401, 'Your session has expired. Please sign in again.')});
    final store = MemorySessionStore('expired-token');
    final auth = AuthProvider(store: store, autoRestore: false);
    await auth.restoreSession();
    await pumpApp(tester, auth);

    expect(auth.status, AuthStatus.unauthenticated);
    expect(store.token, isNull);
    expect(find.byType(LoginScreen), findsOneWidget);
    expect(find.text('Your session has expired. Please sign in again.'), findsOneWidget);
  });

  testWidgets('if the server is unreachable at startup, no private screen is shown', (tester) async {
    ApiClient.instance.httpClient = mockBackend(overrides: {
      'GET /api/auth/me': (_) => throw http.ClientException('offline'),
    });
    final auth = AuthProvider(store: MemorySessionStore('valid-token'), autoRestore: false);
    auth.restoreSession(); // completes inside the pumps below (retry backoff uses the fake clock)
    await pumpApp(tester, auth);
    await settle(tester);
    expect(auth.status, AuthStatus.offline);
    expect(find.byType(OfflineScreen), findsOneWidget);
    expect(find.byType(ShellScreen), findsNothing);
  });

  testWidgets('a 401 during use signs the user out (expired session)', (tester) async {
    var expire = false;
    ApiClient.instance.httpClient = mockBackend(overrides: {
      'GET /api/pantry': (_) => expire ? _err(401, 'expired') : jsonResponse([]),
    });
    final auth = AuthProvider(store: MemorySessionStore('token-123'), autoRestore: false);
    await auth.restoreSession();
    await pumpApp(tester, auth);
    expect(find.byType(ShellScreen), findsOneWidget);

    expire = true;
    await tester.drag(find.byType(Scrollable).first, const Offset(0, 400)); // pull to refresh
    await settle(tester);
    expect(auth.status, AuthStatus.unauthenticated);
    expect(find.byType(LoginScreen), findsOneWidget);
  });

  testWidgets('a second account never sees the first account\'s data', (tester) async {
    var who = 'A';
    ApiClient.instance.httpClient = mockBackend(overrides: {
      'GET /api/auth/me': (_) => jsonResponse(
          {'user': {'id': who == 'A' ? '65f0000000000000000000aa' : '65f0000000000000000000bb', 'name': 'User $who', 'email': '$who@x.com'}}),
      'POST /api/auth/login': (_) => jsonResponse(
          {'access_token': 't$who', 'user': {'id': '65f0000000000000000000bb', 'name': 'User B', 'email': 'b@x.com'}}),
      'GET /api/pantry': (_) => jsonResponse(who == 'A' ? pantryFixture() : []),
    });
    final auth = AuthProvider(store: MemorySessionStore('tA'), autoRestore: false);
    await auth.restoreSession();
    await pumpApp(tester, auth);
    expect(find.textContaining('Cabbage'), findsWidgets);

    await auth.logout();
    who = 'B';
    await auth.login('b@x.com', 'Passw0rd!');
    await settle(tester);
    expect(find.textContaining('User'), findsWidgets);
    expect(find.textContaining('Cabbage'), findsNothing);
  });

  for (final section in [AppSection.meals, AppSection.insights, AppSection.profile, AppSection.settings, AppSection.help]) {
    testWidgets('phone: opening $section from More works (providers reachable from pushed routes)', (tester) async {
      tester.view.physicalSize = const Size(360, 800) * 2;
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.reset);
      ApiClient.instance.httpClient = mockBackend();
      final auth = AuthProvider(store: MemorySessionStore('token-123'), autoRestore: false);
      await auth.restoreSession();
      await pumpApp(tester, auth);
      openSection(tester.element(find.byType(ShellScreen)), section);
      await settle(tester);
      expect(tester.takeException(), isNull);
      expect(find.byType(BackButton), findsOneWidget);
      // Signing out from a pushed page returns to sign-in with the page closed.
      await auth.logout();
      await settle(tester);
      expect(find.byType(LoginScreen), findsOneWidget);
      expect(find.byType(BackButton), findsNothing);
      await tester.pump(const Duration(seconds: 1)); // session providers disposed
    });
  }
}

