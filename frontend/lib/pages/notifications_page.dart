import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../core/api.dart';
import '../core/app_state.dart';
import '../core/utils.dart';
import '../widgets/common.dart';

class NotificationsPage extends StatefulWidget {
  const NotificationsPage({super.key});
  @override
  State<NotificationsPage> createState() => _NotificationsPageState();
}

class _NotificationsPageState extends State<NotificationsPage> {
  List<Map<String, dynamic>> _items = [];
  String _filter = 'ALL';
  String? _error;
  bool _loading = true;

  static const _filters = ['ALL', 'TRADES', 'BOT', 'ALERTS', 'REPORTS'];

  Api get api => context.read<AppState>().api;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final raw = await api.get('/api/notifications');
      final list = raw is Map && raw['items'] is List ? raw['items'] as List : const [];
      if (!mounted) return;
      setState(() {
        _items = [for (final e in list) if (e is Map) Map<String, dynamic>.from(e)];
        _error = null;
        _loading = false;
      });
      final unread = raw is Map ? raw['unread'] : 0;
      if (mounted) context.read<AppState>().setUnreadAlerts(unread is num ? unread.toInt() : 0);
    } on ApiException catch (e) {
      if (mounted) {
        setState(() {
          _error = e.message;
          _loading = false;
        });
      }
    }
  }

  Future<void> _readAll() async {
    try {
      final raw = await api.post('/api/notifications/read-all');
      if (!mounted) return;
      setState(() {
        for (final item in _items) {
          item['seen'] = true;
        }
      });
      final unread = raw is Map ? raw['unread'] : 0;
      context.read<AppState>().setUnreadAlerts(unread is num ? unread.toInt() : 0);
    } on ApiException catch (e) {
      if (mounted) context.toast(e.message, error: true);
    }
  }

  bool _matches(Map<String, dynamic> item) {
    final type = (item['type'] ?? '').toString();
    switch (_filter) {
      case 'TRADES':
        return type.startsWith('TRADE');
      case 'BOT':
        return type == 'BOT_START' || type == 'BOT_STOP' || type == 'ENGINE_DOWN';
      case 'ALERTS':
        return type == 'ALERT' || type == 'ENGINE_DOWN' || type == 'TEST';
      case 'REPORTS':
        return type.contains('REPORT');
      default:
        return true;
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator(color: Palette.brand));
    if (_error != null && _items.isEmpty) return Center(child: ErrorBanner(_error!, onRetry: _load));
    final visible = _items.where(_matches).toList();
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          AppCard(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: context.isDark ? const [Color(0xFF12182B), Color(0xFF161E4A)] : [Colors.white, const Color(0xFFE7EBFF)],
            ),
            child: Row(children: [
              const AppIcon(size: 56),
              const SizedBox(width: 14),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Notification center', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900)),
                const SizedBox(height: 4),
                Text('Entries, starts, stops, and reports arrive here instantly. Nothing is sent by e-mail.', style: TextStyle(color: context.muted, height: 1.35)),
              ])),
            ]),
          ),
          const SizedBox(height: 14),
          Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
            for (final f in _filters)
              SelectChip(
                label: f == 'ALL' ? 'All' : f[0] + f.substring(1).toLowerCase(),
                selected: _filter == f,
                onSelected: () => setState(() => _filter = f),
              ),
            Pressable(onPressed: _readAll, background: Colors.transparent, padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8), icon: const Icon(Icons.done_all_rounded, size: 18), child: const Text('Mark all read')),
          ]),
          const SizedBox(height: 14),
          if (visible.isEmpty)
            const EmptyState(icon: Icons.notifications_none_rounded, title: 'No alerts yet', message: 'A valid entry, a bot start, or a stop will show up here and as a pop-up.')
          else
            for (final item in visible) ...[
              _AlertCard(item: item),
              const SizedBox(height: 10),
            ],
        ],
      ),
    );
  }
}

class _AlertCard extends StatelessWidget {
  final Map<String, dynamic> item;
  const _AlertCard({required this.item});

  @override
  Widget build(BuildContext context) {
    final type = (item['type'] ?? 'ALERT').toString();
    final seen = item['seen'] == true;
    final color = _color(type, (item['severity'] ?? '').toString());
    final when = _when(item['createdAt']);
    return AppCard(
      padding: const EdgeInsets.all(14),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(14)),
          child: Icon(_icon(type), color: color, size: 22),
        ),
        const SizedBox(width: 12),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Text(item['title']?.toString() ?? 'Alert', style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15))),
            if (!seen) Container(width: 8, height: 8, decoration: const BoxDecoration(color: Palette.brand, shape: BoxShape.circle)),
          ]),
          const SizedBox(height: 4),
          Text(item['body']?.toString() ?? '', style: TextStyle(color: context.muted, height: 1.4)),
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
            Tag(type.replaceAll('_', ' '), color),
            Text(when, style: TextStyle(fontSize: 11.5, color: context.muted)),
          ]),
        ])),
      ]),
    );
  }

  static Color _color(String type, String severity) {
    if (severity == 'CRITICAL' || type == 'ENGINE_DOWN') return Palette.red;
    if (type == 'TRADE_OPENED' || type == 'BOT_START') return Palette.green;
    if (type == 'BOT_STOP' || type == 'TRADE_CLOSED' && severity == 'WARNING') return Palette.gold;
    if (type.contains('REPORT')) return Palette.blue;
    return Palette.brand;
  }

  static IconData _icon(String type) {
    switch (type) {
      case 'TRADE_OPENED':
        return Icons.login_rounded;
      case 'TRADE_CLOSED':
        return Icons.flag_rounded;
      case 'BOT_START':
        return Icons.play_arrow_rounded;
      case 'BOT_STOP':
        return Icons.stop_rounded;
      case 'ENGINE_DOWN':
        return Icons.cloud_off_rounded;
      case 'DAILY_REPORT':
      case 'SESSION_REPORT':
        return Icons.insights_rounded;
      default:
        return Icons.notifications_active_rounded;
    }
  }

  static String _when(dynamic raw) {
    if (raw == null) return '';
    DateTime? t;
    if (raw is num) {
      t = DateTime.fromMillisecondsSinceEpoch(raw > 20000000000 ? raw.toInt() : raw.toInt() * 1000, isUtc: true).toLocal();
    } else {
      t = DateTime.tryParse(raw.toString())?.toLocal();
    }
    if (t == null) return '';
    return DateFormat('d MMM, HH:mm').format(t);
  }
}
