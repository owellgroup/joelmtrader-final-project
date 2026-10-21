import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/api.dart';
import '../core/app_state.dart';
import '../core/utils.dart';
import '../widgets/common.dart';
import '../widgets/painters.dart';

class ChartsPage extends StatefulWidget {
  const ChartsPage({super.key});
  @override
  State<ChartsPage> createState() => _ChartsPageState();
}

class _ChartsPageState extends State<ChartsPage> {
  static const symbols = ['XAUUSD', 'EURUSD', 'GBPUSD'];
  static const tfs = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1'];
  static const layerNames = {
    'ema': 'EMA 20/50/200',
    'bb': 'Bollinger',
    'vwap': 'VWAP',
    'zones': 'S/R zones',
    'trend': 'Trendlines',
    'ob': 'Order blocks',
    'fvg': 'Fair value gaps',
    'swings': 'Swings',
    'plan': 'Entry / SL / TP',
  };
  String _symbol = 'EURUSD', _tf = 'M5';
  final Set<String> _layers = {'ema', 'zones', 'trend', 'ob', 'plan', 'swings'};
  Map<String, dynamic>? _data;
  Map<String, dynamic>? _rank;
  String? _error;
  bool _loading = false;
  Offset? _cursor;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _load(silent: true));
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load({bool silent = false}) async {
    if (_loading) return;
    _loading = true;
    if (!silent && mounted) setState(() => _data = null);
    final api = context.read<AppState>().api;
    try {
      final r = await api.get('/api/market/analysis/$_symbol', query: {'tf': _tf, 'bars': 140});
      Map<String, dynamic>? rank;
      try {
        final s = await api.get('/api/market/scan');
        for (final x in (s['rankings'] as List)) {
          if (x['symbol'] == _symbol) rank = Map<String, dynamic>.from(x);
        }
      } catch (_) {}
      if (mounted) {
        setState(() {
          _data = Map<String, dynamic>.from(r);
          _rank = rank;
          _error = null;
        });
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      _loading = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    return ListView(padding: const EdgeInsets.all(16), children: [
      Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
        for (final s in symbols)
          SelectChip(label: s, selected: _symbol == s, style: const TextStyle(fontWeight: FontWeight.w800), onSelected: () {
            setState(() => _symbol = s);
            _load();
          }),
        const SizedBox(width: 12),
        for (final t in tfs)
          SelectChip(label: t, selected: _tf == t, onSelected: () {
            setState(() => _tf = t);
            _load();
          }),
      ]),
      const SizedBox(height: 12),
      AppCard(
        padding: const EdgeInsets.fromLTRB(8, 8, 8, 8),
        child: SizedBox(
          height: MediaQuery.of(context).size.height * 0.55 < 380 ? 380 : MediaQuery.of(context).size.height * 0.55,
          child: _error != null && data == null
              ? Center(child: ErrorBanner(_error!, onRetry: _load))
              : data == null
                  ? const Center(child: CircularProgressIndicator(color: Palette.brand))
                  : MouseRegion(
                      onHover: (e) => setState(() => _cursor = e.localPosition),
                      onExit: (_) => setState(() => _cursor = null),
                      child: GestureDetector(
                        onPanUpdate: (e) => setState(() => _cursor = e.localPosition),
                        onPanEnd: (_) => setState(() => _cursor = null),
                        onLongPressStart: (e) => setState(() => _cursor = e.localPosition),
                        child: CustomPaint(size: Size.infinite, painter: CandlePainter(data, _layers, context.isDark, _cursor)),
                      ),
                    ),
        ),
      ),
      const SizedBox(height: 12),
      AppCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SectionTitle('Overlays', subtitle: 'Toggle the analysis drawn on the chart'),
          Wrap(spacing: 8, runSpacing: 4, children: [
            for (final e in layerNames.entries)
              SelectChip(
                label: e.value,
                selected: _layers.contains(e.key),
                onSelected: () => setState(() => _layers.contains(e.key) ? _layers.remove(e.key) : _layers.add(e.key)),
              ),
          ]),
        ]),
      ),
      const SizedBox(height: 12),
      if (data != null) _analysisPanel(context, data),
    ]);
  }

  Widget _analysisPanel(BuildContext context, Map<String, dynamic> data) {
    final st = Map<String, dynamic>.from(data['structure'] ?? {});
    final plan = data['plan'];
    final r = _rank;
    final digits = i(data['digits'], 5);
    return ResponsiveGrid(minTileWidth: 320, children: [
      AppCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SectionTitle('${data['symbol']} · $_tf structure'),
          _kv('Market structure', st['label']?.toString() ?? '-'),
          _kv('Break of structure', st['bos']?.toString() ?? 'none'),
          _kv('Change of character', st['choch']?.toString() ?? 'none'),
          _kv('Trendlines', '${(data['trendlines'] as List).length} active'),
          _kv('S/R zones', '${(data['zones'] as List).length}'),
          _kv('Order blocks', '${(data['orderBlocks'] as List).length}'),
          _kv('Fair value gaps', '${(data['fvgs'] as List).length}'),
          for (final m in (data['markers'] as List)) _kv('Signal', m['label'].toString()),
        ]),
      ),
      AppCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SectionTitle('Bot verdict'),
          if (r == null)
            Text('No scan data yet.', style: TextStyle(color: context.muted))
          else ...[
            Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
              Tag(r['side'].toString(), r['side'] == 'BUY' ? Palette.green : Palette.red),
              Text('Score ${d(r['score']).toStringAsFixed(0)}', style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 16)),
              Tag(r['tradable'] == true ? 'READY' : 'WAITING', r['tradable'] == true ? Palette.green : Palette.gold),
            ]),
            const SizedBox(height: 10),
            if (plan is Map) ...[
              _kv('Entry', price(plan['entry'], digits)),
              _kv('Stop loss', price(plan['sl'], digits)),
              _kv('Take profit', price(plan['tp'], digits)),
              _kv('Reward : risk', '${plan['rr']}'),
            ],
            const SizedBox(height: 6),
            for (final x in (r['reasons'] as List).take(5)) Padding(padding: const EdgeInsets.symmetric(vertical: 2), child: Text('✓ $x', style: const TextStyle(fontSize: 12))),
            for (final x in (r['blockedReasons'] as List)) Padding(padding: const EdgeInsets.symmetric(vertical: 2), child: Text('✗ $x', style: const TextStyle(fontSize: 12, color: Palette.red))),
          ],
        ]),
      ),
    ]);
  }

  Widget _kv(String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(children: [
          Expanded(child: Text(k, style: TextStyle(color: context.muted, fontSize: 12.5))),
          Flexible(child: Text(v, textAlign: TextAlign.right, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12.5))),
        ]),
      );
}
