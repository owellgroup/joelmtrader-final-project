import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/api.dart';
import '../core/app_state.dart';
import '../core/utils.dart';
import '../widgets/common.dart';

class AdminsPage extends StatefulWidget {
  const AdminsPage({super.key});
  @override
  State<AdminsPage> createState() => _AdminsPageState();
}

class _AdminsPageState extends State<AdminsPage> {
  List? _items;
  String? _error;

  Api get api => context.read<AppState>().api;

  @override
  void initState() {
    super.initState();
    if (context.read<AppState>().isSuper) _load();
  }

  Future<void> _load() async {
    try {
      final r = await api.get('/api/admins');
      if (mounted) setState(() {
        _items = r as List;
        _error = null;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  Future<void> _edit([Map? admin]) async {
    final isNew = admin == null;
    final user = TextEditingController(text: admin?['username']?.toString() ?? '');
    final pass = TextEditingController();
    var enabled = admin?['enabled'] != false;
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => SelectionArea(child: StatefulBuilder(
        builder: (ctx, setS) => AlertDialog(
          title: Text(isNew ? 'Add admin' : 'Edit admin'),
          content: SizedBox(
            width: 380,
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              TextField(controller: user, decoration: const InputDecoration(labelText: 'Username (e-mail)')),
              const SizedBox(height: 12),
              TextField(controller: pass, obscureText: true, decoration: InputDecoration(labelText: isNew ? 'Password (min 8)' : 'New password (leave empty to keep)')),
              if (!isNew && admin['role'] != 'SUPER_ADMIN') ToggleLine(title: 'Account enabled', value: enabled, onChanged: (v) => setS(() => enabled = v)),
            ]),
          ),
          actions: [
            Pressable(onPressed: () => Navigator.pop(ctx, false), padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12), background: Colors.transparent, child: const Text('Cancel')),
            Pressable(onPressed: () => Navigator.pop(ctx, true), background: Palette.brand, foreground: Colors.white, child: Text(isNew ? 'Create' : 'Save')),
          ],
        ),
      )),
    );
    if (ok != true) return;
    try {
      if (isNew) {
        await api.post('/api/admins', body: {'username': user.text.trim(), 'password': pass.text});
      } else {
        await api.put('/api/admins/${admin['id']}', body: {'username': user.text.trim(), if (pass.text.isNotEmpty) 'password': pass.text, 'enabled': enabled});
      }
      if (mounted) context.toast(isNew ? 'Admin created' : 'Admin updated');
      _load();
    } on ApiException catch (e) {
      if (mounted) context.toast(e.message, error: true);
    }
  }

  Future<void> _delete(Map a) async {
    if (!await confirmDialog(context, 'Delete admin?', '${a['username']} will lose access immediately.', confirm: 'Delete', danger: true)) return;
    try {
      await api.delete('/api/admins/${a['id']}');
      if (mounted) context.toast('Admin deleted');
      _load();
    } on ApiException catch (e) {
      if (mounted) context.toast(e.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!context.read<AppState>().isSuper) {
      return const EmptyState(icon: Icons.lock_outline_rounded, title: 'Super admin only', message: 'Only the super admin can add, edit or remove other admins.');
    }
    return Scaffold(
      backgroundColor: Colors.transparent,
      floatingActionButton: FloatingActionButton.extended(onPressed: () => _edit(), icon: const Icon(Icons.person_add_alt_1_rounded), label: const Text('Add admin'), backgroundColor: Palette.brand, foregroundColor: Colors.white),
      body: _items == null
          ? Center(child: _error != null ? ErrorBanner(_error!, onRetry: _load) : const CircularProgressIndicator(color: Palette.brand))
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(padding: const EdgeInsets.fromLTRB(16, 16, 16, 90), children: [
                const SectionTitle('Administrators', subtitle: 'There is no public registration - only you can create admins'),
                for (final a in _items!)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: AppCard(
                      child: LayoutBuilder(builder: (context, c) {
                        final identity = Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          CircleAvatar(backgroundColor: Palette.brand.withOpacity(0.15), child: Icon(a['role'] == 'SUPER_ADMIN' ? Icons.verified_user_rounded : Icons.person_rounded, color: Palette.brand)),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text(a['username'].toString(), style: const TextStyle(fontWeight: FontWeight.w800)),
                              const SizedBox(height: 3),
                              Wrap(spacing: 6, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
                                Tag(a['role'] == 'SUPER_ADMIN' ? 'SUPER ADMIN' : 'ADMIN', a['role'] == 'SUPER_ADMIN' ? Palette.gold : Palette.blue),
                                if (a['enabled'] != true) const Tag('DISABLED', Palette.red),
                                Text('Last login ${fmtDateTime(a['lastLoginAt'])}', style: TextStyle(fontSize: 11, color: context.muted)),
                              ]),
                            ]),
                          ),
                        ]);
                        final actions = Row(mainAxisSize: MainAxisSize.min, children: [
                          IconButton(icon: const Icon(Icons.edit_rounded), onPressed: () => _edit(Map<String, dynamic>.from(a))),
                          if (a['role'] != 'SUPER_ADMIN') IconButton(icon: const Icon(Icons.delete_outline_rounded, color: Palette.red), onPressed: () => _delete(Map<String, dynamic>.from(a))),
                        ]);
                        if (c.maxWidth < 460) {
                          return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                            identity,
                            Align(alignment: Alignment.centerRight, child: actions),
                          ]);
                        }
                        return Row(children: [Expanded(child: identity), actions]);
                      }),
                    ),
                  ),
              ]),
            ),
    );
  }
}
