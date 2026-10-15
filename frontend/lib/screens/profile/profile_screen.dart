import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../main.dart';
import '../../services/api_client.dart';
import '../../services/auth_provider.dart';
import '../../services/pantry_provider.dart';
import '../../services/shopping_provider.dart';
import '../../theme/app_theme.dart';
import '../../widgets/ui.dart';
import '../auth/auth_widgets.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final pantry = context.watch<PantryProvider>();
    final shopping = context.watch<ShoppingProvider>();
    final t = Theme.of(context).textTheme;
    final created = DateTime.tryParse((auth.user?['created_at'] ?? '').toString());
    final household = auth.user?['household_size'];

    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: ListView(
        padding: EdgeInsets.only(bottom: 32 + MediaQuery.paddingOf(context).bottom),
        children: [
          ContentWidth(
            maxWidth: 680,
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              const SizedBox(height: 8),
              AppCard(
                padding: const EdgeInsets.all(20),
                child: Row(children: [
                  CircleAvatar(
                    radius: 32,
                    backgroundColor: AppTheme.lightGreen,
                    child: Text(initialsOf(auth.displayName),
                        style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: AppTheme.primaryDark)),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(auth.displayName, style: t.titleLarge, maxLines: 2, overflow: TextOverflow.ellipsis),
                      const SizedBox(height: 2),
                      Text(auth.email, style: t.bodyMedium, maxLines: 1, overflow: TextOverflow.ellipsis),
                      if (created != null) ...[
                        const SizedBox(height: 4),
                        Text('Member since ${DateFormat('MMMM yyyy').format(created.toLocal())}', style: t.bodySmall),
                      ],
                    ]),
                  ),
                ]),
              ),
              const SectionTitle('Your kitchen'),
              ResponsiveGrid(minItemWidth: 110, children: [
                StatTile(icon: Icons.kitchen_rounded, label: 'In pantry', value: '${pantry.inStock.length}'),
                StatTile(
                    icon: Icons.schedule_rounded, label: 'Use soon', value: '${pantry.expiringSoon.length}', color: AppTheme.warningColor),
                StatTile(
                    icon: Icons.shopping_cart_rounded, label: 'To buy', value: '${shopping.open.length}', color: AppTheme.infoColor),
              ]),
              const SectionTitle('Account'),
              AppCard(
                padding: EdgeInsets.zero,
                child: Column(children: [
                  ListTile(
                    leading: const Icon(Icons.person_outline_rounded),
                    title: const Text('Edit profile'),
                    subtitle: Text(household == null ? 'Name and household' : 'Household of $household'),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => showAppSheet(context, builder: (_) => const _EditProfileForm()),
                  ),
                  const Divider(indent: 56),
                  ListTile(
                    leading: const Icon(Icons.lock_outline_rounded),
                    title: const Text('Change password'),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => showAppSheet(context, builder: (_) => const _ChangePasswordForm()),
                  ),
                  const Divider(indent: 56),
                  ListTile(
                    leading: const Icon(Icons.settings_outlined),
                    title: const Text('Settings'),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => openSection(context, AppSection.settings),
                  ),
                ]),
              ),
              const SizedBox(height: 20),
              OutlinedButton.icon(
                style: OutlinedButton.styleFrom(foregroundColor: AppTheme.dangerColor),
                icon: const Icon(Icons.logout_rounded),
                label: const Text('Sign out'),
                onPressed: () async {
                  final ok = await confirmDialog(context,
                      title: 'Sign out?', message: 'You can sign back in at any time.', confirmLabel: 'Sign out');
                  if (ok && context.mounted) await context.read<AuthProvider>().logout();
                },
              ),
            ]),
          ),
        ],
      ),
    );
  }
}

class _EditProfileForm extends StatefulWidget {
  const _EditProfileForm();

  @override
  State<_EditProfileForm> createState() => _EditProfileFormState();
}

class _EditProfileFormState extends State<_EditProfileForm> {
  final _formKey = GlobalKey<FormState>();
  late final AuthProvider _auth = context.read<AuthProvider>();
  late final _name = TextEditingController(text: _auth.displayName);
  late int? _household = (_auth.user?['household_size'] as num?)?.toInt();
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate() || _saving) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await _auth.updateProfile({'name': _name.text.trim(), if (_household != null) 'household_size': _household});
      if (!mounted) return;
      Navigator.pop(context);
      showAppSnack(context, 'Profile updated');
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _formKey,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text('Edit profile', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 16),
        TextFormField(
          controller: _name,
          textCapitalization: TextCapitalization.words,
          decoration: const InputDecoration(labelText: 'Full name'),
          validator: (v) => (v ?? '').trim().isEmpty ? 'Enter your name' : null,
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<int?>(
          initialValue: _household,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'People in your household'),
          items: [
            const DropdownMenuItem(value: null, child: Text('Not set')),
            for (var i = 1; i <= 10; i++) DropdownMenuItem(value: i, child: Text('$i')),
          ],
          onChanged: (v) => setState(() => _household = v),
        ),
        const SizedBox(height: 8),
        Text('Email: ${_auth.email}', style: Theme.of(context).textTheme.bodySmall),
        if (_error != null) ...[const SizedBox(height: 12), Text(_error!, style: const TextStyle(color: AppTheme.dangerColor))],
        const SizedBox(height: 20),
        LoadingButton(label: 'Save', loading: _saving, onPressed: _save),
      ]),
    );
  }
}

class _ChangePasswordForm extends StatefulWidget {
  const _ChangePasswordForm();

  @override
  State<_ChangePasswordForm> createState() => _ChangePasswordFormState();
}

class _ChangePasswordFormState extends State<_ChangePasswordForm> {
  final _formKey = GlobalKey<FormState>();
  final _current = TextEditingController();
  final _next = TextEditingController();
  final _confirm = TextEditingController();
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate() || _saving) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await context.read<AuthProvider>().changePassword(_current.text, _next.text);
      if (!mounted) return;
      Navigator.pop(context);
      showAppSnack(context, 'Password changed. Other devices have been signed out.');
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _formKey,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text('Change password', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 16),
        PasswordField(
          controller: _current,
          label: 'Current password',
          action: TextInputAction.next,
          validator: (v) => (v ?? '').isEmpty ? 'Enter your current password' : null,
        ),
        const SizedBox(height: 12),
        PasswordField(
          controller: _next,
          label: 'New password',
          action: TextInputAction.next,
          autofillHints: const [AutofillHints.newPassword],
          validator: (v) => (v ?? '').length < 8 ? 'Use at least 8 characters' : null,
        ),
        const SizedBox(height: 12),
        PasswordField(
          controller: _confirm,
          label: 'Confirm new password',
          autofillHints: const [AutofillHints.newPassword],
          validator: (v) => v != _next.text ? 'Passwords do not match' : null,
          onSubmitted: _save,
        ),
        if (_error != null) ...[const SizedBox(height: 12), Text(_error!, style: const TextStyle(color: AppTheme.dangerColor))],
        const SizedBox(height: 20),
        LoadingButton(label: 'Change password', loading: _saving, onPressed: _save),
      ]),
    );
  }
}
