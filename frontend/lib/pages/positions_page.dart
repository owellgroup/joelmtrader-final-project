import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/api.dart';
import '../core/app_state.dart';
import '../core/utils.dart';
import '../widgets/common.dart';

class PositionsPage extends StatelessWidget {
  const PositionsPage({super.key});
  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Column(children: [
        Container(
          margin: const EdgeInsets.fromLTRB(16, 4, 16, 0),
          decoration: BoxDecoration(color: context.cardColor2, borderRadius: BorderRadius.circular(14), border: Border.all(color: context.borderColor)),
          child: TabBar(
            dividerColor: Colors.transparent,
            indicatorSize: TabBarIndicatorSize.tab,
            indicator: BoxDecoration(color: Palette.brand, borderRadius: BorderRadius.circular(12)),
            labelColor: Colors.white,
            unselectedLabelColor: context.muted,
            labelStyle: const TextStyle(fontWeight: FontWeight.w800),
            tabs: const [Tab(text: 'Open trades'), Tab(text: 'Closed trades')],
          ),
        ),
        const Expanded(child: TabBarView(children: [_OpenTab(), _ClosedTab()])),
      ]),
    );
  }
}

class _OpenTab extends StatefulWidget {
  const _OpenTab();
  @override
  State<_OpenTab> createState() => _OpenTabState();
}

class _OpenTabState extends State<_OpenTab> with AutomaticKeepAliveClientMixin {
  List? _items;
  String? _error;
  Timer? _timer;
  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 2), (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final r = await context.read<AppState>().api.get('/api/trades/open');
      if (mounted) setState(() {
        _items = r as List;
        _error = null;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  Future<void> _close(Map t) async {
    if (!await confirmDialog(context, 'Close trade?', 'Close ${t['symbol']} ${t['side']} (#${t['ticket']}) at market now?', confirm: 'Close now', danger: true)) return;
    try {
      await context.read<AppState>().api.post('/api/bot/positions/${t['ticket']}/close');
      if (mounted) context.toast('Trade closed');
      _load();
    } on ApiException catch (e) {
      if (mounted) context.toast(e.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    if (_items == null) return Center(child: _error != null ? ErrorBanner(_error!, onRetry: _load) : const CircularProgressIndicator(color: Palette.brand));
    final total = _items!.fold<double>(0, (a, t) => a + d(t['floatingProfit']));
    return ListView(padding: const EdgeInsets.all(16), children: [
      if (_items!.isEmpty)
        const EmptyState(icon: Icons.hourglass_empty_rounded, title: 'No open trades', message: 'When the bot finds a valid setup it will appear here with live profit/loss.')
      else ...[
        AppCard(
          child: Wrap(spacing: 10, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
            const Icon(Icons.stacked_line_chart_rounded, color: Palette.brand),
            Text('${_items!.length} open', style: const TextStyle(fontWeight: FontWeight.w800)),
            Text('Floating ${money(total, sign: true)}', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 16, color: context.pnl(total))),
          ]),
        ),
        const SizedBox(height: 12),
        ResponsiveGrid(minTileWidth: 380, children: [for (final t in _items!) _openCard(context, Map<String, dynamic>.from(t))]),
      ],
    ]);
  }

  Widget _openCard(BuildContext context, Map<String, dynamic> t) {
    final buy = t['side'] == 'BUY';
    final reasons = (t['reasons'] as List?) ?? [];
    return AppCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(spacing: 8, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
          Text(t['symbol'].toString(), style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 17)),
          Tag(t['side'].toString(), buy ? Palette.green : Palette.red),
          Text('${t['lots']} lots', style: TextStyle(color: context.muted, fontSize: 12)),
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 300),
            child: Text(money(t['floatingProfit'], sign: true), key: ValueKey(money(t['floatingProfit'])), style: TextStyle(fontWeight: FontWeight.w900, fontSize: 20, color: context.pnl(t['floatingProfit']))),
          ),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 18, runSpacing: 6, children: [
          _mini(context, 'Entry', '${t['openPrice']}'),
          _mini(context, 'Current', '${t['currentPrice']}'),
          _mini(context, 'Stop loss', '${t['stopLoss']}'),
          _mini(context, 'Take profit', '${t['takeProfit']}'),
          if (t['score'] != null) _mini(context, 'Score', d(t['score']).toStringAsFixed(0)),
          if (t['setup'] != null) _mini(context, 'Setup', t['setup'].toString().replaceAll('_', ' ')),
        ]),
        if (reasons.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text('Why: ${reasons.take(3).join(' · ')}', maxLines: 3, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 11.5, color: context.muted, height: 1.35)),
          ),
        const SizedBox(height: 10),
        Align(alignment: Alignment.centerRight, child: Pressable(onPressed: () => _close(t), background: Colors.transparent, side: const BorderSide(color: Palette.brand), icon: const Icon(Icons.close_rounded, size: 18), child: const Text('Close trade'))),
      ]),
    );
  }

  Widget _mini(BuildContext context, String k, String v) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(k, style: TextStyle(fontSize: 10.5, color: context.muted)),
        Text(v, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 12.5)),
      ]);
}

class _ClosedTab extends StatefulWidget {
  const _ClosedTab();
  @override
  State<_ClosedTab> createState() => _ClosedTabState();
}

class _ClosedTabState extends State<_ClosedTab> with AutomaticKeepAliveClientMixin {
  final List _items = [];
  int _page = 0, _totalPages = 1, _total = 0;
  bool _loading = false;
  String? _error, _symbol;
  Map<String, dynamic>? _stats;
  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    _items.clear();
    _page = 0;
    _totalPages = 1;
    await _more();
    try {
      final s = await context.read<AppState>().api.get('/api/trades/stats');
      if (mounted) setState(() => _stats = Map<String, dynamic>.from(s));
    } catch (_) {}
  }

  Future<void> _more() async {
    if (_loading || _page >= _totalPages) return;
    setState(() => _loading = true);
    try {
      final r = await context.read<AppState>().api.get('/api/trades/closed', query: {'page': _page, 'size': 30, if (_symbol != null) 'symbol': _symbol});
      if (mounted) setState(() {
        _items.addAll(r['items'] as List);
        _totalPages = i(r['totalPages'], 1);
        _total = i(r['total']);
        _page++;
        _error = null;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView(padding: const EdgeInsets.all(16), children: [
        if (_stats != null)
          ResponsiveGrid(minTileWidth: 170, children: [
            KpiCard(label: 'Net profit', value: money(_stats!['netProfit'], sign: true), icon: Icons.paid_rounded, valueColor: context.pnl(_stats!['netProfit'])),
            KpiCard(label: 'Win rate', value: pct(_stats!['winRate'], digits: 0), icon: Icons.emoji_events_rounded, hint: '${_stats!['wins']}W / ${_stats!['losses']}L'),
            KpiCard(label: 'Avg win', value: money(_stats!['avgWin']), icon: Icons.trending_up_rounded),
            KpiCard(label: 'Avg loss', value: money(_stats!['avgLoss']), icon: Icons.trending_down_rounded),
          ]),
        const SizedBox(height: 12),
        Wrap(spacing: 8, children: [
          for (final s in [null, 'XAUUSD', 'EURUSD', 'GBPUSD'])
            SelectChip(label: s ?? 'All pairs', selected: _symbol == s, onSelected: () {
              setState(() => _symbol = s);
              _reload();
            }),
        ]),
        const SizedBox(height: 12),
        if (_error != null) ErrorBanner(_error!, onRetry: _reload),
        if (_items.isEmpty && !_loading && _error == null) const EmptyState(icon: Icons.inbox_rounded, title: 'No closed trades yet'),
        ResponsiveGrid(minTileWidth: 420, children: [for (final t in _items) _closedCard(context, Map<String, dynamic>.from(t))]),
        if (_page < _totalPages) Padding(padding: const EdgeInsets.all(16), child: Center(child: _loading ? const CircularProgressIndicator(color: Palette.brand) : Pressable(onPressed: _more, background: Colors.transparent, side: const BorderSide(color: Palette.brand), child: Text('Load more ($_total total)')))),
      ]),
    );
  }

  Widget _closedCard(BuildContext context, Map<String, dynamic> t) {
    final net = d(t['netProfit']);
    final result = t['result']?.toString() ?? (net > 0 ? 'WIN' : 'LOSS');
    final col = result == 'WIN' ? Palette.green : (result == 'LOSS' ? Palette.red : Palette.slate);
    return AppCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(spacing: 8, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
          Tag(result, col),
          Text('${t['symbol']} ${t['side']}', style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 15)),
          Text('${t['lots']} lots', style: TextStyle(color: context.muted, fontSize: 12)),
          Text(money(net, sign: true), style: TextStyle(fontWeight: FontWeight.w900, fontSize: 19, color: context.pnl(net))),
        ]),
        const SizedBox(height: 8),
        Text('${t['openPrice']}  →  ${t['closePrice']}   ·   held ${fmtDuration(t['openTime'], t['closeTime'])}', style: const TextStyle(fontSize: 12.5, height: 1.35, fontWeight: FontWeight.w600)),
        const SizedBox(height: 6),
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(Icons.flag_rounded, size: 15, color: col),
          const SizedBox(width: 6),
          Expanded(child: Text(t['remark']?.toString() ?? '-', style: const TextStyle(fontSize: 12.5, height: 1.3))),
        ]),
        const SizedBox(height: 6),
        Text('${fmtDateTime(t['closeTime'])}  ·  balance ${money(t['balanceBefore'] ?? (d(t['balanceAfter']) - net))} → ${money(t['balanceAfter'])}  ·  fees ${money(d(t['commission']) + d(t['swap']))}',
            style: TextStyle(fontSize: 11, color: context.muted)),
      ]),
    );
  }
}
