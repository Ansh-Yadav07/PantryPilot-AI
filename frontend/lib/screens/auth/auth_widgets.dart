import 'package:flutter/material.dart';

import '../../config/app_config.dart';
import '../../main.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/ui.dart';

final _emailRe = RegExp(r'^[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$');

String? validateEmail(String? v) {
  final s = (v ?? '').trim();
  if (s.isEmpty) return 'Enter your email address';
  if (!_emailRe.hasMatch(s)) return 'Enter a valid email address';
  return null;
}

/// Shared frame for the sign-in / sign-up forms: scrolls above the keyboard,
/// centred and width-capped on large screens.
class AuthFrame extends StatelessWidget {
  final String title;
  final String subtitle;
  final Widget form;
  final Widget footer;

  const AuthFrame({super.key, required this.title, required this.subtitle, required this.form, required this.footer});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Center(child: AppLogo(size: 60)),
                  const SizedBox(height: 20),
                  Text(title, style: t.headlineSmall, textAlign: TextAlign.center),
                  const SizedBox(height: 6),
                  Text(subtitle, style: t.bodyMedium, textAlign: TextAlign.center),
                  const SizedBox(height: 28),
                  AppCard(padding: const EdgeInsets.all(20), child: form),
                  const SizedBox(height: 16),
                  footer,
                  const SizedBox(height: 8),
                  const ServerSettingsLink(),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class AuthErrorBanner extends StatelessWidget {
  final String message;
  const AuthErrorBanner(this.message, {super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: AppTheme.dangerLight, borderRadius: BorderRadius.circular(AppTheme.radiusSm)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.error_outline_rounded, color: AppTheme.dangerColor, size: 20),
          const SizedBox(width: 8),
          Expanded(child: Text(message, style: const TextStyle(color: AppTheme.dangerColor, fontSize: 13.5))),
        ],
      ),
    );
  }
}

class PasswordField extends StatefulWidget {
  final TextEditingController controller;
  final String label;
  final String? Function(String?)? validator;
  final TextInputAction action;
  final VoidCallback? onSubmitted;
  final Iterable<String> autofillHints;

  const PasswordField({
    super.key,
    required this.controller,
    this.label = 'Password',
    this.validator,
    this.action = TextInputAction.done,
    this.onSubmitted,
    this.autofillHints = const [AutofillHints.password],
  });

  @override
  State<PasswordField> createState() => _PasswordFieldState();
}

class _PasswordFieldState extends State<PasswordField> {
  bool _obscure = true;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: widget.controller,
      obscureText: _obscure,
      autocorrect: false,
      enableSuggestions: false,
      textInputAction: widget.action,
      autofillHints: widget.autofillHints,
      onFieldSubmitted: (_) => widget.onSubmitted?.call(),
      validator: widget.validator,
      decoration: InputDecoration(
        labelText: widget.label,
        prefixIcon: const Icon(Icons.lock_outline_rounded),
        suffixIcon: IconButton(
          tooltip: _obscure ? 'Show password' : 'Hide password',
          icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
          onPressed: () => setState(() => _obscure = !_obscure),
        ),
      ),
    );
  }
}

/// Shows which server the app talks to, and lets the user change it.
class ServerSettingsLink extends StatefulWidget {
  const ServerSettingsLink({super.key});

  @override
  State<ServerSettingsLink> createState() => _ServerSettingsLinkState();
}

class _ServerSettingsLinkState extends State<ServerSettingsLink> {
  @override
  Widget build(BuildContext context) {
    final configured = AppConfig.isConfigured;
    final host = configured ? Uri.parse(AppConfig.apiBaseUrl).host : null;
    return Center(
      child: TextButton.icon(
        style: TextButton.styleFrom(foregroundColor: configured ? AppTheme.textSecondaryColor : AppTheme.dangerColor),
        icon: Icon(configured ? Icons.dns_outlined : Icons.warning_amber_rounded, size: 18),
        label: Text(configured ? 'Server: $host' : 'Server not configured — tap to set up',
            overflow: TextOverflow.ellipsis),
        onPressed: () async {
          await showServerSettingsDialog(context);
          if (mounted) setState(() {});
        },
      ),
    );
  }
}

Future<void> showServerSettingsDialog(BuildContext context) {
  return showDialog(context: context, builder: (_) => const _ServerDialog());
}

class _ServerDialog extends StatefulWidget {
  const _ServerDialog();

  @override
  State<_ServerDialog> createState() => _ServerDialogState();
}

class _ServerDialogState extends State<_ServerDialog> {
  late final TextEditingController _ctrl =
      TextEditingController(text: AppConfig.isConfigured ? AppConfig.apiBaseUrl.replaceFirst(RegExp(r'/api$'), '') : '');
  String? _error;
  String? _status;
  bool _testing = false;

  Future<void> _save() async {
    final err = AppConfig.validate(_ctrl.text);
    if (err != null) {
      setState(() => _error = err);
      return;
    }
    setState(() {
      _testing = true;
      _error = null;
      _status = null;
    });
    final previous = AppConfig.usingOverride ? AppConfig.apiBaseUrl : null;
    await AppConfig.setOverride(_ctrl.text);
    final ok = await ApiService.ping();
    if (!mounted) return;
    if (ok) {
      Navigator.pop(context);
    } else {
      await AppConfig.setOverride(previous);
      setState(() {
        _testing = false;
        _error = 'Could not reach a PantryPilot server at that address.';
      });
    }
  }

  Future<void> _reset() async {
    await AppConfig.setOverride(null);
    if (mounted) Navigator.pop(context);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Server settings'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('The address of your deployed PantryPilot backend.'),
            const SizedBox(height: 14),
            TextField(
              controller: _ctrl,
              keyboardType: TextInputType.url,
              autocorrect: false,
              decoration: InputDecoration(
                labelText: 'Server URL',
                hintText: 'https://your-api.onrender.com',
                errorText: _error,
              ),
            ),
            if (_status != null) ...[const SizedBox(height: 8), Text(_status!)],
            if (AppConfig.compiledApiUrl.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text('Built-in default: ${AppConfig.compiledApiUrl}', style: Theme.of(context).textTheme.bodySmall),
            ],
          ],
        ),
      ),
      actions: [
        if (AppConfig.usingOverride) TextButton(onPressed: _testing ? null : _reset, child: const Text('Use default')),
        TextButton(onPressed: _testing ? null : () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          onPressed: _testing ? null : _save,
          child: _testing
              ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
              : const Text('Test & save'),
        ),
      ],
    );
  }
}
