import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/api.dart';
import '../core/app_state.dart';
import '../core/utils.dart';
import '../widgets/common.dart';
import '../widgets/painters.dart';

String _rankSummary(Map<String, dynamic> r) {
  final setup = (r['setup'] ?? '').toString().replaceAll('_', ' ');
  final blocked = r['blockedReasons'];
  final blockedList = blocked is List ? blocked : const [];
  final flag = r['tradable'] == true ? 'READY' : (blockedList.isNotEmpty ? blockedList.first.toString() : 'WAITING');
  return '$setup · R:R ${r['rr'] ?? '-'} · $flag';
}

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});
  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  Map<String, dynamic>? _dash;
  List _quotes = [];
  Map<String, dynamic>? _news;
  List _recent = [];
  String? _error;
  bool _busy = false;
  bool _dashLoading = false;
  bool _quotesLoading = false;
  final List<Timer> _timers = [];

  Api get api => context.read<AppState>().api;

  @override
  void initState() {
    super.initState();
    _loadDash();
    _loadQuotes();
    _loadNews();
    _timers.add(Timer.periodic(const Duration(seconds: 3), (_) => _loadDash()));
    _timers.add(Timer.periodic(const Duration(seconds: 2), (_) => _loadQuotes()));
    _timers.add(Timer.periodic(const Duration(seconds: 60), (_) => _loadNews()));
  }

  @override
  void dispose() {
    for (final t in _timers) {
      t.cancel();
    }
    super.dispose();
  }

  Map<String, dynamic> _asMap(dynamic v) => v is Map ? Map<String, dynamic>.from(v) : <String, dynamic>{};

  List _asList(dynamic v) => v is List ? v : const [];

  Future<void> _loadDash() async {
    if (_dashLoading) return;
    _dashLoading = true;
    try {
      final r = await api.get('/api/dashboard');
      if (r is! Map) throw ApiException('Dashboard returned an unexpected response');
      List recent = [];
      try {
        final rc = await api.get('/api/trades/closed', query: {'size': '5'});
        recent = rc is Map ? _asList(rc['items']) : _asList(rc);
      } catch (_) {}
      if (!mounted) return;
      setState(() {
        _dash = Map<String, dynamic>.from(r);
        _recent = recent;
        _error = null;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      _dashLoading = false;
    }
  }

  Future<void> _loadQuotes() async {
    if (_quotesLoading) return;
    _quotesLoading = true;
    try {
      final r = await api.get('/api/market/quotes');
      final list = r is List ? r : (r is Map ? _asList(r['quotes'] ?? r['items']) : const []);
      if (mounted) setState(() => _quotes = list);
    } catch (_) {
    } finally {
      _quotesLoading = false;
    }
  }

  Future<void> _loadNews() async {
    try {
      final r = await api.get('/api/market/news');
      if (r is Map && mounted) setState(() => _news = Map<String, dynamic>.from(r));
    } catch (_) {}
  }

  Future<void> _start() async {
    setState(() => _busy = true);
    try {
      await api.post('/api/bot/start');
      if (mounted) context.toast('Bot started - scanning the markets');
      await _loadDash();
    } on ApiException catch (e) {
      if (mounted) context.toast(e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _stop() async {
    var close = true;
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => StatefulBuilder(
        builder: (ctx, setS) => AlertDialog(
          title: const Text('Stop trading?'),
          content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('The bot will stop scanning and opening trades. A push notification will pop up on your devices.'),
            const SizedBox(height: 8),
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: close,
              onChanged: (v) => setS(() => close = v ?? true),
              title: const Text('Close all open positions now'),
              subtitle: const Text('If unchecked, open trades keep their SL/TP at the broker.'),
            ),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
            FilledButton(style: FilledButton.styleFrom(backgroundColor: Palette.red), onPressed: () => Navigator.pop(ctx, true), child: const Text('Stop trade')),
          ],
        ),
      ),
    );
    if (ok != true) return;
    setState(() => _busy = true);
    try {
      await api.post('/api/bot/stop', body: {'closePositions': close});
      if (mounted) context.toast('Bot stopped. A push notification is on its way.');
      await _loadDash();
    } on ApiException catch (e) {
      if (mounted) context.toast(e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final dash = _dash;
    if (dash == null) {
      return Center(child: _error != null ? Padding(padding: const EdgeInsets.all(24), child: ErrorBanner(_error!, onRetry: _loadDash)) : const CircularProgressIndicator(color: Palette.brand));
    }
    final bot = _asMap(dash['bot']);
    final engine = _asMap(bot['engine']);
    final broker = _asMap(engine['broker']);
    final running = bot['running'] == true;
    final acct = _asMap(dash['account']);
    final all = _asMap(dash['all']);
    final today = _asMap(dash['today']);
    final needsMt5 = engine['mode'] == 'mt5' && broker['connected'] != true;
    final openCount = running ? i(engine['openPositions']) : i(dash['openTrades']);

    final left = <Widget>[
      _RankingCard(scan: dash['scan'] is Map ? Map<String, dynamic>.from(dash['scan'] as Map) : null),
      const SizedBox(height: 16),
      _EquityCard(curve: dash['equityCurve'] is List ? dash['equityCurve'] as List : const []),
      const SizedBox(height: 16),
      _RecentTrades(items: _recent),
    ];
    final right = <Widget>[
      _QuotesCard(quotes: _quotes),
      const SizedBox(height: 16),
      _ActivityCard(items: engine['activity'] is List ? engine['activity'] as List : const []),
      const SizedBox(height: 16),
      _NewsCard(news: _news),
    ];

    return RefreshIndicator(
      onRefresh: _loadDash,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (_error != null) Padding(padding: const EdgeInsets.only(bottom: 12), child: ErrorBanner(_error!)),
          if (bot['engineOnline'] == false)
            Padding(padding: const EdgeInsets.only(bottom: 12), child: ErrorBanner('Trading engine offline: ${bot['engineError'] ?? ''}')),
          if (needsMt5)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: _Mt5LinkCard(message: broker['message']?.toString(), onDone: _loadDash),
            ),
          _Hero(bot: bot, engine: engine, running: running, busy: _busy, onStart: _start, onStop: _stop, scanWhy: (dash['scan'] is Map) ? dash['scan']['why']?.toString() : null),
          const SizedBox(height: 16),
          ResponsiveGrid(minTileWidth: 230, children: [
            KpiCard(label: 'Balance', value: money(acct['balance']), icon: Icons.account_balance_wallet_rounded, hint: acct['stale'] == true ? 'last known' : (acct['login'] != null ? 'Acct ${acct['login']}' : null)),
            KpiCard(label: 'Equity', value: money(acct['equity']), icon: Icons.show_chart_rounded),
            KpiCard(label: 'Floating P/L', value: money(acct['profit'], sign: true), icon: Icons.waves_rounded, valueColor: context.pnl(acct['profit'])),
            KpiCard(label: "Today's P/L", value: money(today['netProfit'], sign: true), icon: Icons.today_rounded, valueColor: context.pnl(today['netProfit']), hint: '${i(today['trades'])} trades closed'),
            KpiCard(label: 'Open trades', value: '$openCount', icon: Icons.lock_open_rounded),
            KpiCard(label: 'Closed trades', value: '${i(dash['closedTrades'])}', icon: Icons.task_alt_rounded, hint: '${i(all['wins'])} wins · ${i(all['losses'])} losses'),
            KpiCard(label: 'Win rate', value: pct(all['winRate'], digits: 0), icon: Icons.emoji_events_rounded),
            KpiCard(label: 'Profit factor', value: d(all['profitFactor']).toStringAsFixed(2), icon: Icons.balance_rounded, hint: 'Net ${money(all['netProfit'], sign: true)}'),
          ]),
          const SizedBox(height: 16),
          LayoutBuilder(builder: (context, c) {
            if (c.maxWidth >= 1000) {
              return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(flex: 3, child: Column(children: left)),
                const SizedBox(width: 16),
                Expanded(flex: 2, child: Column(children: right)),
              ]);
            }
            return Column(children: [...left, const SizedBox(height: 16), ...right]);
          }),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------- hero
class _Hero extends StatelessWidget {
  final Map<String, dynamic> bot, engine;
  final bool running, busy;
  final VoidCallback onStart, onStop;
  final String? scanWhy;
  const _Hero({required this.bot, required this.engine, required this.running, required this.busy, required this.onStart, required this.onStop, this.scanWhy});

  @override
  Widget build(BuildContext context) {
    final status = running ? (engine['status']?.toString() ?? 'RUNNING') : 'STOPPED';
    String headline, sub;
    switch (status) {
      case 'SCANNING':
        headline = 'Scanning the markets';
        sub = 'Ranking XAUUSD, EURUSD and GBPUSD and waiting for a high-quality entry.';
        break;
      case 'IN_TRADE':
        headline = 'Managing open trades';
        sub = 'Trailing stops, protecting profit and scanning for the next opportunity.';
        break;
      case 'COOLDOWN':
        headline = 'Cooling down';
        sub = 'Paused briefly after consecutive losses to protect your balance.';
        break;
      case 'HALTED':
        headline = 'Trading halted by risk manager';
        sub = engine['haltReason']?.toString() ?? '';
        break;
      case 'DISCONNECTED':
        headline = 'MT5 connection lost';
        sub = 'Reconnecting automatically...';
        break;
      default:
        headline = 'Bot is stopped';
        sub = scanWhy ?? 'Press Trade Now to start. The bot will analyse and only trade when conditions are right.';
    }
    final color = status == 'STOPPED' ? Palette.slate : (status == 'HALTED' || status == 'DISCONNECTED' ? Palette.red : Palette.green);
    final stats = Map<String, dynamic>.from(engine['stats'] ?? {});
    return AppCard(
      padding: const EdgeInsets.all(20),
      gradient: LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: context.isDark ? [const Color(0xFF12182B), const Color(0xFF161E4A)] : [Colors.white, const Color(0xFFE7EBFF)],
      ),
      child: LayoutBuilder(builder: (context, c) {
        final narrow = c.maxWidth < 700;
        final info = Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
            StatusPill(status, color, pulse: running),
            if (engine['mode'] == 'paper') const Tag('PAPER MODE', Palette.gold),
            if (engine['mode'] == 'mt5' && engine['broker'] is Map && engine['broker']['demo'] == true) const Tag('DEMO ACCOUNT', Palette.blue),
          ]),
          const SizedBox(height: 12),
          AnimatedSwitcher(duration: const Duration(milliseconds: 300), child: Text(headline, key: ValueKey(headline), style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900))),
          const SizedBox(height: 6),
          Text(sub, style: TextStyle(color: context.muted, height: 1.35)),
          if (running)
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Text('This session: ${i(stats['opened'])} opened · ${i(stats['closed'])} closed · ${money(stats['pnl'], sign: true)}', style: TextStyle(fontWeight: FontWeight.w700, color: context.pnl(stats['pnl']))),
            ),
        ]);
        final stretch = c.maxWidth < 420;
        final trade = _BigButton(label: 'Trade Now', icon: Icons.play_arrow_rounded, color: Palette.green, enabled: !running && !busy, onTap: onStart, busy: busy && !running, expand: stretch);
        final stop = _BigButton(label: 'Stop trade', icon: Icons.stop_rounded, color: Palette.red, enabled: running && !busy, onTap: onStop, busy: busy && running, expand: stretch);
        final buttons = c.maxWidth < 420
            ? Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                trade,
                const SizedBox(height: 10),
                stop,
              ])
            : Wrap(spacing: 12, runSpacing: 10, children: [trade, stop]);
        return narrow
            ? Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [info, const SizedBox(height: 16), buttons])
            : Row(children: [Expanded(child: info), const SizedBox(width: 20), buttons]);
      }),
    );
  }
}

class _BigButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final bool enabled, busy, expand;
  final VoidCallback onTap;
  const _BigButton({required this.label, required this.icon, required this.color, required this.enabled, required this.onTap, this.busy = false, this.expand = false});

  @override
  Widget build(BuildContext context) {
    return AnimatedOpacity(
      duration: const Duration(milliseconds: 250),
      opacity: enabled || busy ? 1 : 0.4,
      child: AnimatedScale(
        duration: const Duration(milliseconds: 250),
        scale: enabled ? 1 : 0.96,
        child: Material(
          color: color,
          borderRadius: BorderRadius.circular(16),
          elevation: enabled ? 4 : 0,
          shadowColor: color.withOpacity(0.5),
          child: InkWell(
            borderRadius: BorderRadius.circular(16),
            onTap: enabled ? onTap : null,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 16),
              child: Row(mainAxisAlignment: MainAxisAlignment.center, mainAxisSize: expand ? MainAxisSize.max : MainAxisSize.min, children: [
                busy ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white)) : Icon(icon, color: Colors.white, size: 24),
                const SizedBox(width: 8),
                Text(label, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w900, fontSize: 15)),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------- ranking
class _RankingCard extends StatelessWidget {
  final Map<String, dynamic>? scan;
  const _RankingCard({this.scan});

  static const labels = {'htf': 'Higher TF', 'momentum': 'Momentum', 'location': 'Location', 'trigger': 'M1 trigger', 'regime': 'Regime', 'volume': 'Volume'};
  static const maxes = {'htf': 30.0, 'momentum': 20.0, 'location': 20.0, 'trigger': 15.0, 'regime': 10.0, 'volume': 5.0};

  @override
  Widget build(BuildContext context) {
    final ranks = (scan?['rankings'] as List?) ?? [];
    final chosen = scan?['chosen']?.toString();
    return AppCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const SectionTitle('Opportunity ranking', subtitle: 'All 3 pairs scored across D1 · H4 · H1 · M30 · M15 · M5 · M1'),
        if (ranks.isEmpty)
          const EmptyState(icon: Icons.radar_rounded, title: 'Waiting for market data', message: 'Connect your MT5 account in Settings (or use paper mode).')
        else ...[
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: (chosen != null ? Palette.green : Palette.gold).withOpacity(0.10), borderRadius: BorderRadius.circular(12)),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(chosen != null ? Icons.check_circle_rounded : Icons.hourglass_top_rounded, size: 18, color: chosen != null ? Palette.green : Palette.gold),
              const SizedBox(width: 8),
              Expanded(child: Text(scan?['why']?.toString() ?? '', style: const TextStyle(fontSize: 12.5, height: 1.4))),
            ]),
          ),
          const SizedBox(height: 12),
          for (final r in ranks)
            if (r is Map) _RankRow(r: Map<String, dynamic>.from(r), selected: r['symbol'] == chosen),
        ],
      ]),
    );
  }
}

class _RankRow extends StatelessWidget {
  final Map<String, dynamic> r;
  final bool selected;
  const _RankRow({required this.r, required this.selected});

  @override
  Widget build(BuildContext context) {
    final score = d(r['score']);
    final buy = r['side'] == 'BUY';
    final barColor = score >= 62 ? Palette.green : (score >= 45 ? Palette.gold : Palette.slate);
    final comps = Map<String, dynamic>.from(r['components'] ?? {});
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: selected ? Palette.green : context.borderColor, width: selected ? 1.6 : 1),
        color: selected ? Palette.green.withOpacity(0.05) : null,
      ),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
          childrenPadding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
          shape: const Border(),
          collapsedShape: const Border(),
          title: Wrap(spacing: 8, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
            Text(r['symbol'].toString(), style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 15)),
            Tag(r['side'].toString(), buy ? Palette.green : Palette.red),
            if (selected) const Tag('SELECTED', Palette.brand),
            Text(score.toStringAsFixed(0), style: TextStyle(fontWeight: FontWeight.w900, fontSize: 20, color: barColor)),
          ]),
          subtitle: Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              TweenAnimationBuilder<double>(
                tween: Tween(begin: 0, end: (score / 100).clamp(0.0, 1.0)),
                duration: const Duration(milliseconds: 700),
                curve: Curves.easeOutCubic,
                builder: (_, v, __) => ClipRRect(borderRadius: BorderRadius.circular(6), child: LinearProgressIndicator(value: v, minHeight: 8, color: barColor, backgroundColor: barColor.withOpacity(0.15))),
              ),
              const SizedBox(height: 6),
              Text(_rankSummary(r), maxLines: 2, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 11.5, color: context.muted)),
            ]),
          ),
          children: [
            Align(
              alignment: Alignment.centerLeft,
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Wrap(spacing: 8, runSpacing: 8, children: [
                  for (final k in _RankingCard.labels.keys)
                    Container(
                      width: 118,
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(color: context.bgColor, borderRadius: BorderRadius.circular(10)),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(_RankingCard.labels[k]!, style: TextStyle(fontSize: 10.5, color: context.muted)),
                        const SizedBox(height: 3),
                        Text('${d(comps[k]).toStringAsFixed(1)} / ${_RankingCard.maxes[k]!.toStringAsFixed(0)}', style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 12)),
                      ]),
                    ),
                ]),
                const SizedBox(height: 10),
                if (r['plan'] is Map)
                  Text('Entry ${r['plan']['entry']}  ·  SL ${r['plan']['sl']}  ·  TP ${r['plan']['tp']}  ·  lots ${r['lots']}  ·  risk ${money(r['riskAmount'])}',
                      style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12)),
                if (d(r['riskPctAtMinLot']) > 0) Text('Risk at minimum lot: ${pct(r['riskPctAtMinLot'])} of equity', style: TextStyle(fontSize: 11.5, color: context.muted)),
                const SizedBox(height: 8),
                for (final x in (r['reasons'] as List? ?? [])) _bullet(context, x.toString(), Palette.green, Icons.check_rounded),
                for (final x in (r['penalties'] as List? ?? [])) _bullet(context, x.toString(), Palette.gold, Icons.remove_rounded),
                for (final x in (r['blockedReasons'] as List? ?? [])) _bullet(context, x.toString(), Palette.red, Icons.block_rounded),
              ]),
            ),
          ],
        ),
      ),
    );
  }

  Widget _bullet(BuildContext context, String t, Color c, IconData icon) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(icon, size: 15, color: c),
          const SizedBox(width: 6),
          Expanded(child: Text(t, style: const TextStyle(fontSize: 12, height: 1.3))),
        ]),
      );
}

// ---------------------------------------------------------------------------- equity
class _EquityCard extends StatelessWidget {
  final List curve;
  const _EquityCard({required this.curve});
  @override
  Widget build(BuildContext context) {
    final vals = [for (final p in curve) if (p is Map) d(p['equity'])];
    final up = vals.length < 2 || vals.last >= vals.first;
    return AppCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SectionTitle('Equity curve', subtitle: vals.length < 2 ? null : '${money(vals.first)}  →  ${money(vals.last)}'),
        SizedBox(
          height: 190,
          child: vals.length < 2
              ? const EmptyState(icon: Icons.timeline_rounded, title: 'No data yet', message: 'Account snapshots appear a minute after the bot starts.')
              : TweenAnimationBuilder<double>(
                  tween: Tween(begin: 0, end: 1),
                  duration: const Duration(milliseconds: 900),
                  builder: (_, v, __) => CustomPaint(size: Size.infinite, painter: LineAreaPainter(vals, up ? Palette.green : Palette.red, showAxis: true, textColor: context.muted, progress: v)),
                ),
        ),
      ]),
    );
  }
}

// ---------------------------------------------------------------------------- quotes
class _QuotesCard extends StatelessWidget {
  final List quotes;
  const _QuotesCard({required this.quotes});
  @override
  Widget build(BuildContext context) {
    return AppCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const SectionTitle('Live market', subtitle: 'Real-time quotes from MT5'),
        if (quotes.whereType<Map>().isEmpty) const Padding(padding: EdgeInsets.all(12), child: Text('Waiting for quotes...')),
        for (final raw in quotes)
          if (raw is Map)
            Builder(builder: (context) {
              final q = Map<String, dynamic>.from(raw);
              final sparkRaw = q['spark'];
              final spark = sparkRaw is List ? [for (final v in sparkRaw) d(v)] : <double>[];
              return Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Row(children: [
              Expanded(
                flex: 3,
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(q['symbol'].toString(), style: const TextStyle(fontWeight: FontWeight.w900)),
                  Text('Spread ${price(q['spread'], i(q['digits']))}', style: TextStyle(fontSize: 11, color: context.muted)),
                ]),
              ),
              Expanded(
                flex: 3,
                child: SizedBox(height: 34, child: spark.length < 2 ? const SizedBox.shrink() : CustomPaint(painter: LineAreaPainter(spark, (d(q['changePct']) >= 0) ? Palette.green : Palette.red))),
              ),
              Expanded(
                flex: 3,
                child: Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  Text(price(q['bid'], i(q['digits'])), style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 15)),
                  if (q['changePct'] != null) Text('${d(q['changePct']) >= 0 ? '+' : ''}${d(q['changePct']).toStringAsFixed(2)}%', style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700, color: context.pnl(q['changePct']))),
                ]),
              ),
            ]),
          );
            }),
      ]),
    );
  }
}

// ---------------------------------------------------------------------------- activity
class _ActivityCard extends StatelessWidget {
  final List items;
  const _ActivityCard({required this.items});
  @override
  Widget build(BuildContext context) {
    return AppCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const SectionTitle('Bot activity', subtitle: 'What the bot is doing right now'),
        if (items.whereType<Map>().isEmpty) Text('No activity yet.', style: TextStyle(color: context.muted)),
        for (final raw in items.take(10))
          if (raw is Map)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(fmtTime(raw['time']), style: TextStyle(fontSize: 11, color: context.muted, fontFeatures: const [FontFeature.tabularFigures()])),
                const SizedBox(width: 10),
                Expanded(child: Text((raw['message'] ?? '').toString(), style: TextStyle(fontSize: 12.5, color: raw['level'] == 'critical' || raw['level'] == 'warning' ? Palette.red : null))),
              ]),
            ),
      ]),
    );
  }
}

// ---------------------------------------------------------------------------- news
class _NewsCard extends StatelessWidget {
  final Map<String, dynamic>? news;
  const _NewsCard({this.news});
  @override
  Widget build(BuildContext context) {
    final events = (news?['events'] is List ? news!['events'] as List : const [])
        .where((e) => e is Map && d(e['time']) > DateTime.now().millisecondsSinceEpoch / 1000 - 1800)
        .take(4)
        .toList();
    final heads = (news?['headlines'] is List ? news!['headlines'] as List : const []).whereType<Map>().take(5).toList();
    return AppCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const SectionTitle('USD / EUR / GBP news', subtitle: 'The bot stands aside around high-impact events'),
        for (final e in events)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 5),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Wrap(spacing: 8, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
                Tag(e['impact'].toString().toUpperCase(), e['impact'] == 'High' ? Palette.red : Palette.gold),
                Text('${e['currency']}', style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 12)),
                Text(fmtDateTime(e['time']), style: TextStyle(fontSize: 11, color: context.muted)),
              ]),
              const SizedBox(height: 2),
              Text(e['title'].toString(), style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600, height: 1.3)),
            ]),
          ),
        if (events.isNotEmpty && heads.isNotEmpty) const Divider(height: 18),
        for (final h in heads)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Icon(Icons.fiber_manual_record, size: 8, color: Palette.brand),
              const SizedBox(width: 8),
              Expanded(child: Text(h['title'].toString(), maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12.5, height: 1.3))),
            ]),
          ),
        if (events.isEmpty && heads.isEmpty) Text('News feed unavailable right now.', style: TextStyle(color: context.muted)),
      ]),
    );
  }
}

// ---------------------------------------------------------------------------- recent
class _RecentTrades extends StatelessWidget {
  final List items;
  const _RecentTrades({required this.items});
  @override
  Widget build(BuildContext context) {
    return AppCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const SectionTitle('Recent closed trades'),
        if (items.whereType<Map>().isEmpty) Text('No closed trades yet.', style: TextStyle(color: context.muted)),
        for (final raw in items)
          if (raw is Map)
            ListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              leading: Icon(d(raw['netProfit']) >= 0 ? Icons.trending_up_rounded : Icons.trending_down_rounded, color: context.pnl(raw['netProfit'])),
              title: Text('${raw['symbol']} ${raw['side']} · ${raw['lots']} lots', style: const TextStyle(fontWeight: FontWeight.w700)),
              subtitle: Text(raw['remark']?.toString() ?? '', maxLines: 1, overflow: TextOverflow.ellipsis),
            trailing: Text(money(raw['netProfit'], sign: true), style: TextStyle(fontWeight: FontWeight.w900, color: context.pnl(raw['netProfit']))),
          ),
      ]),
    );
  }
}

/// MT5 account login. The Flutter app sends the credentials to the Java API,
/// which forwards them to the Python engine. The engine logs the MT5 terminal in.
class _Mt5LinkCard extends StatefulWidget {
  final String? message;
  final Future<void> Function() onDone;
  const _Mt5LinkCard({this.message, required this.onDone});

  @override
  State<_Mt5LinkCard> createState() => _Mt5LinkCardState();
}

class _Mt5LinkCardState extends State<_Mt5LinkCard> {
  final _login = TextEditingController();
  final _server = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  bool _hide = true;

  @override
  void dispose() {
    _login.dispose();
    _server.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    if (_login.text.trim().isEmpty || _server.text.trim().isEmpty || _password.text.isEmpty) {
      context.toast('Enter the MT5 account number, server, and trading password', error: true);
      return;
    }
    setState(() => _busy = true);
    try {
      final api = context.read<AppState>().api;
      final r = await api.put('/api/settings/mt5', body: {
        'login': _login.text.trim(),
        'server': _server.text.trim(),
        'password': _password.text,
      });
      _password.clear();
      final res = r is Map ? r['connectResult'] : null;
      final ok = res is Map && res['connected'] == true;
      if (!mounted) return;
      context.toast(ok ? 'Connected to MT5' : 'Saved, but MT5 did not connect: ${res is Map ? (res['message'] ?? '') : ''}', error: !ok);
      await widget.onDone();
    } on ApiException catch (e) {
      if (mounted) context.toast(e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final superAdmin = context.watch<AppState>().isSuper;
    return AppCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const SectionTitle('Log in to your MT5 account', subtitle: 'The bot trades this account. Use the trading password, not the investor password.'),
        if ((widget.message ?? '').isNotEmpty)
          Padding(padding: const EdgeInsets.only(bottom: 10), child: Text(widget.message!, style: const TextStyle(color: Palette.red, fontSize: 12.5))),
        ResponsiveGrid(minTileWidth: 220, children: [
          TextField(controller: _login, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'MT5 login', hintText: 'Account number')),
          TextField(controller: _server, decoration: const InputDecoration(labelText: 'Broker server', hintText: 'e.g. Exness-MT5Trial')),
          TextField(
            controller: _password,
            obscureText: _hide,
            decoration: InputDecoration(
              labelText: 'Trading password',
              suffixIcon: IconButton(icon: Icon(_hide ? Icons.visibility_off_outlined : Icons.visibility_outlined), onPressed: () => setState(() => _hide = !_hide)),
            ),
          ),
        ]),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: (_busy || !superAdmin) ? null : _connect,
          icon: _busy ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Icon(Icons.link_rounded),
          label: const Text('Connect MT5'),
        ),
        if (!superAdmin) Padding(padding: const EdgeInsets.only(top: 6), child: Text('Only the super admin can link the broker account.', style: TextStyle(fontSize: 11.5, color: context.muted))),
      ]),
    );
  }
}
