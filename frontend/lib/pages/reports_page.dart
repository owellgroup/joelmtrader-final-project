import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/api.dart';
import '../core/app_state.dart';
import '../core/utils.dart';
import '../widgets/common.dart';

class ReportsPage extends StatefulWidget {
  const ReportsPage({super.key});
  @override
  State<ReportsPage> createState() => _ReportsPageState();
}

class _ReportsPageState extends State<ReportsPage> {
  List? _items;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Api get api => context.read<AppState>().api;

  Future<void> _load() async {
    try {
      final r = await api.get('/api/reports/sessions');
      if (mounted) setState(() {
        _items = r as List;
        _error = null;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  Future<void> _act(Future<dynamic> Function() f, String okMsg) async {
    try {
      await f();
      if (mounted) context.toast(okMsg);
    } on ApiException catch (e) {
      if (mounted) context.toast(e.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_items == null) return Center(child: _error != null ? ErrorBanner(_error!, onRetry: _load) : const CircularProgressIndicator(color: Palette.brand));
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(padding: const EdgeInsets.all(16), children: [
        AppCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const SectionTitle('Session reports', subtitle: 'A push notification is sent whenever you press Stop trade'),
            LayoutBuilder(builder: (context, c) {
              final narrow = c.maxWidth < 520;
              final daily = OutlinedButton.icon(
                onPressed: () => _act(() => api.post('/api/reports/daily'), 'Daily digest requested (only sent if trades closed today)'),
                icon: const Icon(Icons.today_rounded, size: 18),
                label: const Text('Send daily digest'),
              );
              final test = OutlinedButton.icon(
                onPressed: () => _act(() => api.post('/api/settings/test-email'), 'Test push sent'),
                icon: const Icon(Icons.notifications_active_rounded, size: 18),
                label: const Text('Test push'),
              );
              if (narrow) {
                return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  daily,
                  const SizedBox(height: 8),
                  test,
                ]);
              }
              return Wrap(spacing: 8, runSpacing: 8, children: [daily, test]);
            }),
          ]),
        ),
        const SizedBox(height: 16),
        if (_items!.isEmpty) const EmptyState(icon: Icons.insights_rounded, title: 'No sessions yet', message: 'Press Trade Now on the dashboard to start your first session.'),
        ResponsiveGrid(minTileWidth: 280, children: [for (final s in _items!) _card(context, Map<String, dynamic>.from(s))]),
      ]),
    );
  }

  Widget _card(BuildContext context, Map<String, dynamic> s) {
    final st = Map<String, dynamic>.from(s['stats'] ?? {});
    final open = s['openingBalance'], close = s['closingBalance'];
    final net = (open != null && close != null) ? d(close) - d(open) : d(st['netProfit']);
    final running = s['status'] == 'RUNNING';
    return AppCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(spacing: 8, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
          Text('Session #${s['id']}', style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 15)),
          Tag(s['status'].toString(), running ? Palette.green : (s['status'] == 'FAILED' ? Palette.red : Palette.slate)),
          if (!running) Text(money(net, sign: true), style: TextStyle(fontWeight: FontWeight.w900, fontSize: 18, color: context.pnl(net))),
        ]),
        const SizedBox(height: 6),
        Text('${fmtDateTime(s['startedAt'])}  →  ${s['stoppedAt'] == null ? 'now' : fmtDateTime(s['stoppedAt'])}', style: TextStyle(fontSize: 12, height: 1.35, color: context.muted)),
        const SizedBox(height: 10),
        Wrap(spacing: 18, runSpacing: 6, children: [
          _kv(context, 'Opening', money(open)),
          _kv(context, 'Closing', close == null ? '-' : money(close)),
          _kv(context, 'Trades', '${i(st['trades'])}'),
          _kv(context, 'Win rate', pct(st['winRate'], digits: 0)),
          _kv(context, 'Profit factor', d(st['profitFactor']).toStringAsFixed(2)),
        ]),
        if (s['note'] != null) Padding(padding: const EdgeInsets.only(top: 6), child: Text(s['note'].toString(), style: const TextStyle(fontSize: 11.5, color: Palette.gold))),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
          Icon(s['emailSent'] == true ? Icons.notifications_active_rounded : Icons.notifications_off_rounded, size: 16, color: s['emailSent'] == true ? Palette.green : context.muted),
          Text(s['emailSent'] == true ? 'Push sent' : 'Not pushed', style: TextStyle(fontSize: 12.5, color: context.muted)),
          if (!running)
            TextButton(
              onPressed: () => _act(() => api.post('/api/reports/sessions/${s['id']}/resend'), 'Push queued'),
              child: const Text('Send push again'),
            ),
        ]),
      ]),
    );
  }

  Widget _kv(BuildContext context, String k, String v) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(k, style: TextStyle(fontSize: 10.5, color: context.muted)),
        Text(v, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13)),
      ]);
}
