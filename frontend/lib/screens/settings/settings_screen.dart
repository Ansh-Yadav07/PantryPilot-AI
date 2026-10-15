import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../config/app_config.dart';
import '../../main.dart';
import '../../services/api_service.dart';
import '../../services/auth_provider.dart';
import '../../services/yolo_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/ui.dart';
import '../auth/auth_widgets.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool? _serverOk;
  bool _checking = false;
  String? _modelStatus;

  Future<void> _checkServer() async {
    setState(() => _checking = true);
    final ok = await ApiService.ping();
    if (mounted) {
      setState(() {
        _serverOk = ok;
        _checking = false;
      });
    }
  }

  Future<void> _checkModel() async {
    setState(() => _modelStatus = 'Loading…');
    try {
      await YoloService.initialize();
      if (mounted) setState(() => _modelStatus = 'Ready · ${YoloService.labels.length} vegetables');
    } catch (e) {
      if (mounted) setState(() => _modelStatus = 'Unavailable on this device');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: EdgeInsets.only(bottom: 32 + MediaQuery.paddingOf(context).bottom),
        children: [
          ContentWidth(
            maxWidth: 680,
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              const SectionTitle('Account'),
              AppCard(
                padding: EdgeInsets.zero,
                child: Column(children: [
                  ListTile(
                    leading: const Icon(Icons.person_outline_rounded),
                    title: const Text('Profile & password'),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => openSection(context, AppSection.profile),
                  ),
                  const Divider(indent: 56),
                  ListTile(
                    leading: const Icon(Icons.logout_rounded, color: AppTheme.dangerColor),
                    title: const Text('Sign out', style: TextStyle(color: AppTheme.dangerColor)),
                    onTap: () async {
                      final ok = await confirmDialog(context, title: 'Sign out?', message: 'You can sign back in at any time.', confirmLabel: 'Sign out');
                      if (ok && context.mounted) await context.read<AuthProvider>().logout();
                    },
                  ),
                ]),
              ),
              const SectionTitle('Connection'),
              AppCard(
                padding: EdgeInsets.zero,
                child: Column(children: [
                  ListTile(
                    leading: const Icon(Icons.dns_outlined),
                    title: const Text('Server'),
                    subtitle: Text(AppConfig.isConfigured ? AppConfig.apiBaseUrl : 'Not configured',
                        maxLines: 2, overflow: TextOverflow.ellipsis),
                    trailing: const Icon(Icons.edit_outlined, size: 20),
                    onTap: () async {
                      await showServerSettingsDialog(context);
                      if (mounted) setState(() => _serverOk = null);
                    },
                  ),
                  const Divider(indent: 56),
                  ListTile(
                    leading: Icon(
                      _serverOk == null ? Icons.wifi_tethering_rounded : (_serverOk! ? Icons.check_circle_rounded : Icons.error_outline_rounded),
                      color: _serverOk == null ? null : (_serverOk! ? AppTheme.primaryColor : AppTheme.dangerColor),
                    ),
                    title: const Text('Test connection'),
                    subtitle: Text(_serverOk == null ? 'Check that the server is reachable' : (_serverOk! ? 'Connected' : 'Server unreachable')),
                    trailing: _checking ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : null,
                    onTap: _checking ? null : _checkServer,
                  ),
                ]),
              ),
              const SectionTitle('Vegetable detection'),
              AppCard(
                padding: EdgeInsets.zero,
                child: ListTile(
                  leading: const Icon(Icons.memory_rounded),
                  title: const Text('On-device model'),
                  subtitle: Text(_modelStatus ?? 'YOLO26s · runs offline on this device. Tap to check.'),
                  onTap: YoloService.isSupported ? _checkModel : null,
                ),
              ),
              const SectionTitle('Your data'),
              AppCard(
                child: Text(
                  'Your pantry, shopping list, expenses and meal plans are stored in your PantryPilot account in the cloud, '
                  'so they need an internet connection. Vegetable photos are analysed on your device and are never uploaded. '
                  'Receipt photos are sent to the server to be read and are not stored.',
                  style: t.bodyMedium,
                ),
              ),
              const SizedBox(height: 20),
              Center(child: Text('PantryPilot AI · version 1.1.0', style: t.bodySmall)),
            ]),
          ),
        ],
      ),
    );
  }
}
