import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'config/app_config.dart';
import 'screens/auth/login_screen.dart';
import 'screens/dashboard/dashboard_screen.dart';
import 'screens/help/help_screen.dart';
import 'screens/meal_planner/meal_planner_screen.dart';
import 'screens/notifications/notifications_screen.dart';
import 'screens/pantry/pantry_screen.dart';
import 'screens/profile/profile_screen.dart';
import 'screens/recipes/recipes_screen.dart';
import 'screens/settings/settings_screen.dart';
import 'screens/shopping/shopping_list_screen.dart';
import 'screens/smart_dashboard/smart_dashboard_screen.dart';
import 'services/auth_provider.dart';
import 'services/pantry_provider.dart';
import 'services/shopping_provider.dart';
import 'theme/app_theme.dart';

final GlobalKey<NavigatorState> rootNavigatorKey = GlobalKey<NavigatorState>();

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AppConfig.load();
  runApp(
    ChangeNotifierProvider(
      create: (_) => AuthProvider(),
      child: const PantryPilotApp(),
    ),
  );
}

class PantryPilotApp extends StatelessWidget {
  const PantryPilotApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'PantryPilot AI',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      navigatorKey: rootNavigatorKey,
      // Session data sits above the Navigator so every pushed page
      // (profile, scanners, recipe details...) can reach it.
      builder: (context, child) => _SessionProviders(child: child ?? const SizedBox.shrink()),
      home: const AuthGate(),
    );
  }
}

/// Chooses what to show from the authentication state. Private screens are
/// only built once the server has confirmed the session.
class AuthGate extends StatefulWidget {
  const AuthGate({super.key});

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  AuthStatus? _last;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    if (_last == AuthStatus.authenticated && auth.status != AuthStatus.authenticated) {
      // Signed out or session expired: close any pages opened on top.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        rootNavigatorKey.currentState?.popUntil((r) => r.isFirst);
      });
    }
    _last = auth.status;

    switch (auth.status) {
      case AuthStatus.restoring:
        return const SplashScreen();
      case AuthStatus.offline:
        return OfflineScreen(message: auth.errorMessage);
      case AuthStatus.unauthenticated:
        return const LoginScreen();
      case AuthStatus.authenticated:
        return const ShellScreen();
    }
  }
}

/// Installs [SessionScope] while signed in. Keyed by user id, so signing in as
/// someone else always starts from fresh, empty state.
class _SessionProviders extends StatefulWidget {
  final Widget child;
  const _SessionProviders({required this.child});

  @override
  State<_SessionProviders> createState() => _SessionProvidersState();
}

class _SessionProvidersState extends State<_SessionProviders> {
  String? _userId; // user whose providers are currently installed
  Timer? _disposeTimer;

  @override
  void dispose() {
    _disposeTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    if (auth.isAuthenticated) {
      _disposeTimer?.cancel();
      _disposeTimer = null;
      _userId = auth.userId;
    } else if (_userId != null) {
      // Signed out: pages that used this session are being closed (see
      // AuthGate). Keep the old providers until their exit animations finish,
      // then dispose them so no data from the session stays in memory.
      _disposeTimer ??= Timer(const Duration(milliseconds: 600), () {
        _disposeTimer = null;
        if (mounted && !auth.isAuthenticated) setState(() => _userId = null);
      });
    }
    if (_userId == null) return widget.child;
    return SessionScope(key: ValueKey(_userId), child: widget.child);
  }
}

/// Data providers that live exactly as long as one signed-in session.
class SessionScope extends StatelessWidget {
  final Widget child;
  const SessionScope({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => PantryProvider()..load()),
        ChangeNotifierProvider(create: (_) => ShoppingProvider()..load()),
        ChangeNotifierProvider(create: (_) => NavProvider()),
      ],
      child: child,
    );
  }
}

class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const AppLogo(size: 72),
            const SizedBox(height: 20),
            Text('PantryPilot AI', style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 6),
            Text('Smarter food. Less waste.', style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: 32),
            const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2.5)),
          ],
        ),
      ),
    );
  }
}

class OfflineScreen extends StatelessWidget {
  final String? message;
  const OfflineScreen({super.key, this.message});

  @override
  Widget build(BuildContext context) {
    final auth = context.read<AuthProvider>();
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.cloud_off_rounded, size: 56, color: AppTheme.textSecondaryColor),
                  const SizedBox(height: 16),
                  Text("Can't reach PantryPilot", style: Theme.of(context).textTheme.titleLarge, textAlign: TextAlign.center),
                  const SizedBox(height: 8),
                  Text(
                    message ?? 'Check your internet connection and try again.',
                    style: Theme.of(context).textTheme.bodyMedium,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 24),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton(onPressed: auth.restoreSession, child: const Text('Try again')),
                  ),
                  const SizedBox(height: 8),
                  TextButton(onPressed: auth.logout, child: const Text('Sign out')),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class AppLogo extends StatelessWidget {
  final double size;
  const AppLogo({super.key, this.size = 56});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: AppTheme.primaryColor,
        borderRadius: BorderRadius.circular(size * 0.28),
      ),
      child: Icon(Icons.eco_rounded, color: Colors.white, size: size * 0.55),
    );
  }
}

// ── Navigation ──────────────────────────────────────────────────────────

enum AppSection { home, pantry, shopping, recipes, meals, insights, profile, settings, help }

class NavProvider extends ChangeNotifier {
  AppSection _section = AppSection.home;
  AppSection get section => _section;

  void go(AppSection s) {
    if (s == _section) return;
    _section = s;
    notifyListeners();
  }
}

class _Dest {
  final AppSection section;
  final String label;
  final IconData icon;
  final IconData selectedIcon;
  const _Dest(this.section, this.label, this.icon, this.selectedIcon);
}

const _primaryDests = [
  _Dest(AppSection.home, 'Home', Icons.home_outlined, Icons.home_rounded),
  _Dest(AppSection.pantry, 'Pantry', Icons.kitchen_outlined, Icons.kitchen_rounded),
  _Dest(AppSection.shopping, 'Shopping', Icons.shopping_cart_outlined, Icons.shopping_cart_rounded),
  _Dest(AppSection.recipes, 'Recipes', Icons.restaurant_menu_outlined, Icons.restaurant_menu_rounded),
];

const _secondaryDests = [
  _Dest(AppSection.meals, 'Meal planner', Icons.calendar_month_outlined, Icons.calendar_month_rounded),
  _Dest(AppSection.insights, 'Insights & expenses', Icons.insights_outlined, Icons.insights_rounded),
  _Dest(AppSection.profile, 'Profile', Icons.person_outline_rounded, Icons.person_rounded),
  _Dest(AppSection.settings, 'Settings', Icons.settings_outlined, Icons.settings_rounded),
  _Dest(AppSection.help, 'Help & support', Icons.help_outline_rounded, Icons.help_rounded),
];

Widget pageFor(AppSection s) {
  switch (s) {
    case AppSection.home:
      return const DashboardScreen();
    case AppSection.pantry:
      return const PantryScreen();
    case AppSection.shopping:
      return const ShoppingListScreen();
    case AppSection.recipes:
      return const RecipesScreen();
    case AppSection.meals:
      return const MealPlannerScreen();
    case AppSection.insights:
      return const SmartDashboardScreen();
    case AppSection.profile:
      return const ProfileScreen();
    case AppSection.settings:
      return const SettingsScreen();
    case AppSection.help:
      return const HelpScreen();
  }
}

/// Opens a section. On phones, sections outside the bottom bar open as a
/// normal page (so the system back button returns to where you were).
void openSection(BuildContext context, AppSection s) {
  final isPrimary = _primaryDests.any((d) => d.section == s);
  if (isPrimary || ShellScreen.isWide(context)) {
    context.read<NavProvider>().go(s);
  } else {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => pageFor(s)));
  }
}

void openNotifications(BuildContext context) {
  Navigator.of(context).push(MaterialPageRoute(builder: (_) => const NotificationsScreen()));
}

class ShellScreen extends StatelessWidget {
  const ShellScreen({super.key});

  static bool isWide(BuildContext context) => MediaQuery.sizeOf(context).width >= 900;

  @override
  Widget build(BuildContext context) {
    final nav = context.watch<NavProvider>();
    final wide = isWide(context);
    final section = nav.section;

    if (wide) {
      return Scaffold(
        body: Row(
          children: [
            _Sidebar(current: section),
            const VerticalDivider(width: 1),
            Expanded(child: KeyedSubtree(key: ValueKey(section), child: pageFor(section))),
          ],
        ),
      );
    }

    // Phones: secondary sections are pushed as pages, so the body only ever
    // shows one of the four primary tabs.
    final primary = _primaryDests.any((d) => d.section == section) ? section : AppSection.home;
    final index = _primaryDests.indexWhere((d) => d.section == primary);
    return PopScope(
      canPop: primary == AppSection.home,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) nav.go(AppSection.home);
      },
      child: Scaffold(
        body: IndexedStack(
          index: index,
          children: [for (final d in _primaryDests) pageFor(d.section)],
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: index,
          onDestinationSelected: (i) {
            if (i == _primaryDests.length) {
              _showMoreSheet(context);
            } else {
              nav.go(_primaryDests[i].section);
            }
          },
          destinations: [
            for (final d in _primaryDests)
              NavigationDestination(icon: Icon(d.icon), selectedIcon: Icon(d.selectedIcon), label: d.label),
            const NavigationDestination(icon: Icon(Icons.menu_rounded), label: 'More'),
          ],
        ),
      ),
    );
  }

  void _showMoreSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      useSafeArea: true,
      isScrollControlled: true,
      builder: (ctx) => SingleChildScrollView(
        padding: const EdgeInsets.only(bottom: 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.notifications_none_rounded),
              title: const Text('Expiry alerts'),
              onTap: () {
                Navigator.pop(ctx);
                openNotifications(context);
              },
            ),
            for (final d in _secondaryDests)
              ListTile(
                leading: Icon(d.icon),
                title: Text(d.label),
                onTap: () {
                  Navigator.pop(ctx);
                  openSection(context, d.section);
                },
              ),
          ],
        ),
      ),
    );
  }
}

class _Sidebar extends StatelessWidget {
  final AppSection current;
  const _Sidebar({required this.current});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    Widget item(_Dest d) {
      final selected = d.section == current;
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: ListTile(
          dense: true,
          selected: selected,
          selectedTileColor: AppTheme.lightGreen,
          selectedColor: AppTheme.primaryDark,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppTheme.radiusSm)),
          leading: Icon(selected ? d.selectedIcon : d.icon, size: 22),
          title: Text(d.label,
              style: TextStyle(fontSize: 14.5, fontWeight: selected ? FontWeight.w600 : FontWeight.w500)),
          onTap: () => context.read<NavProvider>().go(d.section),
        ),
      );
    }

    return SizedBox(
      width: 248,
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 20),
              child: Row(
                children: [
                  const AppLogo(size: 36),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text('PantryPilot', style: Theme.of(context).textTheme.titleLarge, overflow: TextOverflow.ellipsis),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                children: [
                  for (final d in _primaryDests) item(d),
                  const Padding(padding: EdgeInsets.symmetric(vertical: 10), child: Divider()),
                  for (final d in _secondaryDests) item(d),
                  const SizedBox(height: 2),
                  ListTile(
                    dense: true,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppTheme.radiusSm)),
                    leading: const Icon(Icons.notifications_none_rounded, size: 22),
                    title: const Text('Expiry alerts', style: TextStyle(fontSize: 14.5, fontWeight: FontWeight.w500)),
                    onTap: () => openNotifications(context),
                  ),
                ],
              ),
            ),
            const Divider(),
            ListTile(
              leading: CircleAvatar(
                radius: 16,
                backgroundColor: AppTheme.lightGreen,
                child: Text(initialsOf(auth.displayName),
                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppTheme.primaryDark)),
              ),
              title: Text(auth.displayName, maxLines: 1, overflow: TextOverflow.ellipsis),
              subtitle: Text(auth.email, maxLines: 1, overflow: TextOverflow.ellipsis),
              onTap: () => context.read<NavProvider>().go(AppSection.profile),
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }
}

String initialsOf(String name) {
  final parts = name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
  if (parts.isEmpty) return '?';
  if (parts.length == 1) return parts.first[0].toUpperCase();
  return (parts.first[0] + parts.last[0]).toUpperCase();
}
