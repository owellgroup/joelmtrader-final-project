import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/gestures.dart';
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
  static const symbols = ['XAUUSD', 'GBPJPY', 'EURJPY', 'EURUSD', 'GBPUSD'];
  static const tfs = ['M1', 'M5', 'M10', 'M15', 'M30', 'H1', 'H4', 'D1'];
  static const tfLabel = {'M1': '1m', 'M5': '5m', 'M10': '10m', 'M15': '15m', 'M30': '30m', 'H1': '1H', 'H4': '4H', 'D1': 'D'};
  static const layerNames = {
    'ema': 'EMA 9/20/50/200',
    'bb': 'Bollinger',
    'vwap': 'VWAP',
    'zones': 'S/R zones',
    'trend': 'Trendlines',
    'ob': 'Order blocks',
    'fvg': 'Fair value gaps',
    'swings': 'Swings',
    'pivots': 'Daily pivots',
    'session': 'Session highs / lows',
    'liq': 'Equal highs / lows',
    'plan': 'Entry / SL / TP',
  };
  String _symbol = 'XAUUSD', _tf = 'M5';
  final Set<String> _layers = {'ema', 'zones', 'trend', 'ob', 'plan', 'swings', 'pivots', 'session'};
  Map<String, dynamic>? _data;
  Map<String, dynamic>? _rank;
  String? _error;
  bool _loading = false;
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
    if (_loading && silent) return;
    final reqSymbol = _symbol;
    final reqTf = _tf;
    _loading = true;
    if (!silent && mounted) {
      setState(() {
        _data = null;
        _rank = null;
        _error = null;
      });
    }
    final api = context.read<AppState>().api;
    try {
      final r = await api.get('/api/market/analysis/$reqSymbol', query: {'tf': reqTf, 'bars': 140});
      Map<String, dynamic>? rank;
      try {
        final s = await api.get('/api/market/scan');
        for (final x in (s['rankings'] as List)) {
          if (x['symbol'] == reqSymbol) rank = Map<String, dynamic>.from(x);
        }
      } catch (_) {}
      // Drop stale responses if the user switched symbol/TF mid-request.
      if (!mounted || reqSymbol != _symbol || reqTf != _tf) return;
      setState(() {
        _data = Map<String, dynamic>.from(r);
        _rank = rank;
        _error = null;
      });
    } on ApiException catch (e) {
      if (!mounted || reqSymbol != _symbol || reqTf != _tf) return;
      final msg = e.message;
      // Never leave JPY charts stuck on the old "unsupported" wording.
      final friendly = msg.toLowerCase().contains('unsupported')
          ? 'Engine/API still needs a redeploy for $reqSymbol. After redeploy, Retry.'
          : msg;
      setState(() => _error = friendly);
    } finally {
      if (reqSymbol == _symbol && reqTf == _tf) _loading = false;
    }
  }

  void _pickSymbol(String s) {
    if (s == _symbol) return;
    _loading = false; // allow the new request immediately
    setState(() {
      _symbol = s;
      _data = null;
      _rank = null;
      _error = null;
    });
    _load();
  }

  void _pickTf(String t) {
    if (t == _tf) return;
    _loading = false;
    setState(() {
      _tf = t;
      _data = null;
      _rank = null;
      _error = null;
    });
    _load();
  }

  void _openIndicators() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: context.cardColor2,
      builder: (ctx) {
        return StatefulBuilder(builder: (ctx, setSheet) {
          return SafeArea(
            child: ListView(shrinkWrap: true, children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                child: Text('Indicators', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: ctx.textColor)),
              ),
              for (final e in layerNames.entries)
                InkWell(
                  onTap: () {
                    setState(() => _layers.contains(e.key) ? _layers.remove(e.key) : _layers.add(e.key));
                    setSheet(() {});
                  },
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    child: Row(children: [
                      SizedBox(
                        width: 40,
                        child: Icon(_layers.contains(e.key) ? Icons.check_rounded : null, color: Palette.brand, size: 18),
                      ),
                      Expanded(child: Text(e.value, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14))),
                    ]),
                  ),
                ),
              const SizedBox(height: 8),
            ]),
          );
        });
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    final narrow = MediaQuery.sizeOf(context).width < 720;
    return Padding(
      padding: EdgeInsets.fromLTRB(narrow ? 8 : 12, 8, narrow ? 8 : 12, 8),
      child: Column(children: [
        Expanded(
          flex: narrow ? 8 : 7,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: context.isDark ? const Color(0xFF0E1424) : Colors.white,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: context.borderColor),
            ),
            child: Column(children: [
              _toolbar(context),
              Divider(height: 1, color: context.borderColor),
              Expanded(
                child: _error != null && data == null
                    ? Center(child: ErrorBanner(_error!, onRetry: _load))
                    : data == null
                        ? const Center(child: CircularProgressIndicator(color: Palette.brand))
                        : (data['error'] != null && ((data['candles'] as List?) ?? const []).length < 5)
                            ? Center(child: ErrorBanner(data['error'].toString(), onRetry: _load))
                            : _ChartBoard(key: ValueKey('$_symbol|$_tf'), data: data, layers: _layers, dark: context.isDark),
              ),
            ]),
          ),
        ),
        if (data != null) ...[
          const SizedBox(height: 8),
          Expanded(flex: narrow ? 4 : 3, child: SingleChildScrollView(child: _analysisPanel(context, data))),
        ],
      ]),
    );
  }

  Widget _toolbar(BuildContext context) {
    return SizedBox(
      height: 42,
      child: Row(children: [
        PopupMenuButton<String>(
          tooltip: 'Symbol',
          onSelected: _pickSymbol,
          itemBuilder: (ctx) => [
            for (final s in symbols)
              PopupMenuItem(
                value: s,
                height: 40,
                child: Row(children: [
                  SizedBox(width: 22, child: _symbol == s ? const Icon(Icons.check_rounded, size: 16, color: Palette.brand) : null),
                  Text(s, style: TextStyle(fontWeight: _symbol == s ? FontWeight.w800 : FontWeight.w600)),
                ]),
              ),
          ],
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Text(_symbol, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14)),
              Icon(Icons.arrow_drop_down_rounded, size: 20, color: context.muted),
            ]),
          ),
        ),
        Container(width: 1, height: 18, color: context.borderColor),
        Expanded(
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 4),
            children: [
              for (final t in tfs)
                InkWell(
                  onTap: () => _pickTf(t),
                  borderRadius: BorderRadius.circular(6),
                  child: Container(
                    alignment: Alignment.center,
                    padding: const EdgeInsets.symmetric(horizontal: 10),
                    decoration: BoxDecoration(
                      border: Border(bottom: BorderSide(color: _tf == t ? Palette.brand : Colors.transparent, width: 2)),
                    ),
                    child: Text(
                      tfLabel[t]!,
                      style: TextStyle(fontSize: 13, fontWeight: _tf == t ? FontWeight.w800 : FontWeight.w600, color: _tf == t ? Palette.brand : context.muted),
                    ),
                  ),
                ),
            ],
          ),
        ),
        IconButton(
          tooltip: 'Indicators',
          visualDensity: VisualDensity.compact,
          onPressed: _openIndicators,
          icon: Icon(Icons.functions_rounded, size: 20, color: context.textColor),
        ),
      ]),
    );
  }

  Widget _analysisPanel(BuildContext context, Map<String, dynamic> data) {
    final st = Map<String, dynamic>.from(data['structure'] ?? {});
    final plan = data['plan'];
    final analysis = Map<String, dynamic>.from(data['analysis'] ?? {});
    final stack = Map<String, dynamic>.from(analysis['stack'] ?? {});
    final r = _rank;
    final digits = i(data['digits'], 5);
    return ResponsiveGrid(minTileWidth: 320, children: [
      AppCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SectionTitle('${data['symbol']} · top-down read'),
          if ((analysis['story'] ?? '').toString().isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(analysis['story'].toString(), style: const TextStyle(fontSize: 12.5, height: 1.35)),
            ),
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final tf in ['D1', 'H4', 'H1', 'M30', 'M15', 'M10', 'M5', 'M1'])
              if (stack[tf] is Map)
                Tag(
                  '$tf ${_tfArrow(stack[tf])}',
                  d(stack[tf]['trend']) > 0.05 ? Palette.green : (d(stack[tf]['trend']) < -0.05 ? Palette.red : Palette.slate),
                ),
          ]),
          const SizedBox(height: 8),
          _kv('Market structure', st['label']?.toString() ?? '-'),
          _kv('Break of structure', st['bos']?.toString() ?? 'none'),
          _kv('Change of character', st['choch']?.toString() ?? 'none'),
          _kv('Daily / H4 lock', analysis['htfLock']?.toString() ?? 'WAIT'),
          _kv('Trendlines', '${(data['trendlines'] as List? ?? const []).length} active'),
          _kv('S/R zones', '${(data['zones'] as List? ?? const []).length}'),
          _kv('Order blocks', '${(data['orderBlocks'] as List? ?? const []).length}'),
          _kv('Fair value gaps', '${(data['fvgs'] as List? ?? const []).length}'),
          _kv('Pivots', '${(data['pivots'] as List? ?? const []).length}'),
          _kv('Session levels', '${(data['sessions'] as List? ?? const []).length}'),
          _kv('Liquidity pools', '${(data['liquidity'] as List? ?? const []).length}'),
          for (final m in (data['markers'] as List? ?? const [])) _kv('Signal', m['label'].toString()),
          for (final t in (analysis['tools'] as List? ?? const []).take(6))
            Padding(padding: const EdgeInsets.symmetric(vertical: 2), child: Text('• $t', style: const TextStyle(fontSize: 12))),
        ]),
      ),
      AppCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SectionTitle('Bot verdict'),
          if (r == null)
            Text('No scan data yet.', style: TextStyle(color: context.muted))
          else ...[
            Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
              Tag(r['side'].toString(), r['side'] == 'BUY' ? Palette.green : (r['side'] == 'SELL' ? Palette.red : Palette.slate)),
              Text('Score ${d(r['score']).toStringAsFixed(0)}', style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 16)),
              Tag(r['tradable'] == true ? 'READY' : 'WAITING', r['tradable'] == true ? Palette.green : Palette.gold),
              if (r['htfLock'] != null) Tag('HTF ${r['htfLock']}', Palette.brand),
            ]),
            const SizedBox(height: 10),
            if (plan is Map) ...[
              _kv('Entry', price(plan['entry'], digits)),
              _kv('Stop loss', price(plan['sl'], digits)),
              _kv('Take profit', price(plan['tp'], digits)),
              _kv('Reward : risk', '${plan['rr']}'),
            ],
            const SizedBox(height: 6),
            for (final x in (r['reasons'] as List? ?? const []).take(6)) Padding(padding: const EdgeInsets.symmetric(vertical: 2), child: Text('✓ $x', style: const TextStyle(fontSize: 12))),
            for (final x in (r['blockedReasons'] as List? ?? const [])) Padding(padding: const EdgeInsets.symmetric(vertical: 2), child: Text('✗ $x', style: const TextStyle(fontSize: 12, color: Palette.red))),
          ],
        ]),
      ),
    ]);
  }

  String _tfArrow(dynamic row) {
    final trend = d(row is Map ? row['trend'] : 0);
    if (trend > 0.08) return '↑';
    if (trend < -0.08) return '↓';
    return '→';
  }

  Widget _kv(String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(children: [
          Expanded(child: Text(k, style: TextStyle(color: context.muted, fontSize: 12.5))),
          Flexible(child: Text(v, textAlign: TextAlign.right, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12.5))),
        ]),
      );
}

/// Drag to pan, pinch or scroll to zoom, drag the price scale to resize price.
/// Opens on the fitted view and stays there until you move it.
class _ChartBoard extends StatefulWidget {
  final Map<String, dynamic> data;
  final Set<String> layers;
  final bool dark;
  const _ChartBoard({super.key, required this.data, required this.layers, required this.dark});

  @override
  State<_ChartBoard> createState() => _ChartBoardState();
}

class _ChartBoardState extends State<_ChartBoard> {
  bool _fitted = true;
  double _start = -0.5;
  double _span = 20;
  double _priceZoom = 1;
  double _priceShift = 0;
  Offset? _cursor;
  double _scale0 = 1;

  int get _n => ((widget.data['candles'] as List?) ?? const []).length;

  void _leaveFit() {
    if (_fitted) {
      _fitted = false;
      _start = -0.5;
      _span = _n + 2;
    }
  }

  void _reset() => setState(() {
        _fitted = true;
        _priceZoom = 1;
        _priceShift = 0;
        _cursor = null;
      });

  void _clamp() {
    final n = _n.toDouble();
    _span = _span.clamp(8, math.max(8, n * 3));
    final minStart = -_span * 0.2;
    final maxStart = math.max(minStart, n - _span * 0.25);
    _start = _start.clamp(minStart, maxStart);
  }

  void _zoom(double focalDx, double plotW, double factor) {
    _leaveFit();
    final count0 = _span;
    final idx = _start + focalDx / (plotW / count0);
    _span = (_span * factor).clamp(8, math.max(8, _n * 3));
    _start = idx - focalDx / (plotW / _span);
    _clamp();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, c) {
      final plotW = math.max(1.0, c.maxWidth - CandlePainter.rightPad);
      final timeAxis = c.maxHeight - CandlePainter.bottomPad;
      return Listener(
        onPointerSignal: (e) {
          if (e is! PointerScrollEvent) return;
          setState(() => _zoom(e.localPosition.dx.clamp(0, plotW), plotW, e.scrollDelta.dy > 0 ? 1.12 : 0.88));
        },
        child: GestureDetector(
          onDoubleTap: _reset,
          onLongPressStart: (e) => setState(() => _cursor = e.localPosition),
          onLongPressMoveUpdate: (e) => setState(() => _cursor = e.localPosition),
          onLongPressEnd: (_) => setState(() => _cursor = null),
          onScaleStart: (e) => _scale0 = 1,
          onScaleUpdate: (e) {
            setState(() {
              final local = e.localFocalPoint;
              final onPrice = local.dx >= c.maxWidth - CandlePainter.rightPad;
              final onTime = local.dy >= timeAxis;
              if (e.pointerCount >= 2) {
                final factor = _scale0 / e.scale;
                if ((factor - 1).abs() > 0.001) _zoom(local.dx.clamp(0, plotW), plotW, factor);
                _scale0 = e.scale;
              } else if (onPrice) {
                _priceZoom = (_priceZoom * (1 - e.focalPointDelta.dy / 220)).clamp(0.35, 8);
                _priceShift = (_priceShift + e.focalPointDelta.dy / 500).clamp(-2, 2);
              } else if (onTime) {
                _leaveFit();
                _span = (_span * (1 - e.focalPointDelta.dx / 280)).clamp(8, math.max(8, _n * 3));
                _clamp();
              } else {
                _leaveFit();
                _start -= e.focalPointDelta.dx / (plotW / _span);
                _clamp();
              }
            });
          },
          child: MouseRegion(
            onHover: (e) => setState(() => _cursor = e.localPosition),
            onExit: (_) => setState(() => _cursor = null),
            child: Stack(children: [
              CustomPaint(
                size: Size.infinite,
                painter: CandlePainter(
                  widget.data,
                  widget.layers,
                  widget.dark,
                  _cursor,
                  viewStart: _fitted ? null : _start,
                  viewSpan: _fitted ? null : _span,
                  priceZoom: _priceZoom,
                  priceShift: _priceShift,
                ),
              ),
              if (!_fitted || _priceZoom != 1 || _priceShift != 0)
                Positioned(
                  left: 6,
                  bottom: 26,
                  child: TextButton(
                    onPressed: _reset,
                    style: TextButton.styleFrom(
                      visualDensity: VisualDensity.compact,
                      foregroundColor: widget.dark ? const Color(0xFFCBD5E1) : const Color(0xFF334155),
                      backgroundColor: (widget.dark ? Colors.black : Colors.white).withValues(alpha: 0.72),
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    ),
                    child: const Text('Reset', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
                  ),
                ),
            ]),
          ),
        ),
      );
    });
  }
}
