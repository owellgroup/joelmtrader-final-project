import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../core/utils.dart';

/// Smooth area line chart (equity curve / sparklines) - no external chart package needed.
class LineAreaPainter extends CustomPainter {
  final List<double> values;
  final Color color;
  final bool showAxis;
  final Color textColor;
  final double progress;
  LineAreaPainter(this.values, this.color, {this.showAxis = false, this.textColor = Colors.grey, this.progress = 1});

  @override
  void paint(Canvas canvas, Size size) {
    if (values.length < 2) return;
    final left = showAxis ? 46.0 : 0.0;
    final w = size.width - left, h = size.height - (showAxis ? 4 : 0);
    var mn = values.reduce(math.min), mx = values.reduce(math.max);
    if ((mx - mn).abs() < 1e-9) {
      mx += 1;
      mn -= 1;
    }
    final pad = (mx - mn) * 0.12;
    mn -= pad;
    mx += pad;
    double x(int idx) => left + w * idx / (values.length - 1);
    double y(double v) => h - (v - mn) / (mx - mn) * h;
    final end = ((values.length - 1) * progress).clamp(1, values.length - 1).toInt();
    final path = Path()..moveTo(x(0), y(values[0]));
    for (var k = 1; k <= end; k++) {
      final cx = (x(k - 1) + x(k)) / 2;
      path.cubicTo(cx, y(values[k - 1]), cx, y(values[k]), x(k), y(values[k]));
    }
    final fill = Path.from(path)
      ..lineTo(x(end), h)
      ..lineTo(x(0), h)
      ..close();
    canvas.drawPath(
        fill,
        Paint()
          ..shader = LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [color.withOpacity(0.28), color.withOpacity(0.0)])
              .createShader(Rect.fromLTWH(0, 0, size.width, h)));
    canvas.drawPath(path, Paint()..color = color..style = PaintingStyle.stroke..strokeWidth = 2.4..strokeCap = StrokeCap.round);
    if (showAxis) {
      final grid = Paint()..color = textColor.withOpacity(0.12)..strokeWidth = 1;
      for (var g = 0; g <= 3; g++) {
        final v = mn + (mx - mn) * g / 3;
        final yy = y(v);
        canvas.drawLine(Offset(left, yy), Offset(size.width, yy), grid);
        final tp = TextPainter(text: TextSpan(text: v.toStringAsFixed(2), style: TextStyle(color: textColor, fontSize: 10)), textDirection: TextDirection.ltr)..layout();
        tp.paint(canvas, Offset(0, yy - tp.height / 2));
      }
    }
    canvas.drawCircle(Offset(x(end), y(values[end])), 4, Paint()..color = color);
  }

  @override
  bool shouldRepaint(covariant LineAreaPainter old) => old.values != values || old.progress != progress || old.color != color;
}

/// Full candlestick chart with all analysis overlays drawn by the engine.
class CandlePainter extends CustomPainter {
  final Map<String, dynamic> data;
  final Set<String> layers;
  final bool dark;
  final Offset? cursor;
  /// Left edge as a candle index. Null keeps the original fitted view.
  final double? viewStart;
  /// How many candles fit across the plot. Null keeps the original fitted view.
  final double? viewSpan;
  final double priceZoom;
  final double priceShift;
  CandlePainter(this.data, this.layers, this.dark, this.cursor, {this.viewStart, this.viewSpan, this.priceZoom = 1, this.priceShift = 0});

  static const double rightPad = 64, bottomPad = 22, topPad = 8;

  @override
  void paint(Canvas canvas, Size size) {
    final candles = (data['candles'] as List?) ?? [];
    if (candles.length < 5) return;
    final digits = i(data['digits'], 5);
    final tfSec = d(data['tfSeconds'], 60);
    final n = candles.length;
    final t0 = d(candles[0][0]);
    final fg = dark ? const Color(0xFFCBD5E1) : const Color(0xFF334155);
    final grid = (dark ? Colors.white : Colors.black).withOpacity(0.07);
    final chartW = size.width - rightPad, chartH = size.height - bottomPad - topPad;
    final fitted = viewSpan == null || viewStart == null;
    final span = fitted ? n + 2.0 : viewSpan!.clamp(8, n * 3).toDouble();
    final start = fitted ? -0.5 : viewStart!;
    final cw = chartW / span;

    // ---- price range from the candles actually on screen
    var lo = double.infinity, hi = -double.infinity;
    final i0 = start.floor().clamp(0, n - 1).toInt();
    final i1 = (start + span).ceil().clamp(i0, n - 1).toInt();
    for (var k = i0; k <= i1; k++) {
      final c = candles[k];
      lo = math.min(lo, d(c[3]));
      hi = math.max(hi, d(c[2]));
    }
    final plan = data['plan'];
    void include(double v) {
      if (v > 0 && v > lo - (hi - lo) * 0.8 && v < hi + (hi - lo) * 0.8) {
        lo = math.min(lo, v);
        hi = math.max(hi, v);
      }
    }
    if (layers.contains('plan') && plan is Map) {
      for (final k in ['entry', 'sl', 'tp']) {
        include(d(plan[k]));
      }
    }
    if (layers.contains('pivots')) {
      for (final pv in (data['pivots'] as List? ?? [])) {
        include(d(pv['price']));
      }
    }
    if (layers.contains('session')) {
      for (final s in (data['sessions'] as List? ?? [])) {
        include(d(s['high']));
        include(d(s['low']));
      }
    }
    final padR = (hi - lo) * 0.06;
    lo -= padR;
    hi += padR;
    if (priceZoom != 1 || priceShift != 0) {
      final mid = (hi + lo) / 2;
      final half = (hi - lo) / 2 / priceZoom.clamp(0.35, 8);
      final shift = priceShift * (hi - lo);
      lo = mid - half + shift;
      hi = mid + half + shift;
    }
    double yOf(double p) => topPad + (hi - p) / (hi - lo) * chartH;
    double xOfIdx(double idx) => (idx - start) * cw;
    double xOfT(num t) => xOfIdx((t - t0) / tfSec);
    final rect = Rect.fromLTWH(0, topPad, chartW, chartH);

    canvas.save();
    canvas.clipRect(Rect.fromLTWH(0, 0, size.width, size.height));
    // ---- grid + price axis
    for (var g = 0; g <= 5; g++) {
      final p = lo + (hi - lo) * g / 5;
      final yy = yOf(p);
      canvas.drawLine(Offset(0, yy), Offset(chartW, yy), Paint()..color = grid);
      _text(canvas, p.toStringAsFixed(digits), Offset(chartW + 6, yy - 6), fg.withOpacity(0.8), 10);
    }
    // ---- time axis
    final step = math.max(1, (n / 6).round());
    for (var k = 0; k < n; k += step) {
      final t = parseTime(candles[k][0]);
      if (t == null) continue;
      final label = tfSec >= 86400 ? '${t.day}/${t.month}' : '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
      _text(canvas, label, Offset(xOfIdx(k.toDouble()) - 14, size.height - 16), fg.withOpacity(0.7), 9.5);
    }
    canvas.save();
    canvas.clipRect(rect);

    // ---- zones
    if (layers.contains('zones')) {
      for (final z in (data['zones'] as List? ?? [])) {
        final sup = z['kind'] == 'support';
        final col = sup ? Palette.green : Palette.red;
        final r = Rect.fromLTRB(0, yOf(d(z['high'])), chartW, math.max(yOf(d(z['low'])), yOf(d(z['high'])) + 3));
        canvas.drawRect(r, Paint()..color = col.withOpacity(0.11));
        canvas.drawLine(r.topLeft, r.topRight, Paint()..color = col.withOpacity(0.55)..strokeWidth = 1);
        canvas.drawLine(r.bottomLeft, r.bottomRight, Paint()..color = col.withOpacity(0.55)..strokeWidth = 1);
        _text(canvas, '${sup ? 'S' : 'R'} ${(z['tfs'] as List).join('/')}', Offset(4, r.top + 2), col, 9.5, bold: true);
      }
    }
    // ---- FVG & order blocks
    if (layers.contains('fvg')) {
      for (final g in (data['fvgs'] as List? ?? [])) {
        final col = g['type'] == 'bullish' ? Colors.purple : Colors.deepOrange;
        final x = math.max(0.0, xOfT(d(g['t'])));
        final r = Rect.fromLTRB(x, yOf(d(g['high'])), chartW, yOf(d(g['low'])));
        canvas.drawRect(r, Paint()..color = col.withOpacity(0.10));
        _text(canvas, 'FVG', Offset(x + 3, r.top + 1), col, 9, bold: true);
      }
    }
    if (layers.contains('ob')) {
      for (final o in (data['orderBlocks'] as List? ?? [])) {
        final bull = o['type'] == 'bullish';
        final col = bull ? Palette.blue : Palette.gold;
        final x = math.max(0.0, xOfT(d(o['t'])));
        final r = Rect.fromLTRB(x, yOf(d(o['high'])), chartW, yOf(d(o['low'])));
        canvas.drawRect(r, Paint()..color = col.withOpacity(0.16));
        canvas.drawRect(r, Paint()..color = col.withOpacity(0.8)..style = PaintingStyle.stroke..strokeWidth = 1.2);
        _text(canvas, bull ? 'Bull OB' : 'Bear OB', Offset(x + 3, r.top + 1), col, 9.5, bold: true);
      }
    }
    // ---- indicators
    final ind = (data['indicators'] as Map?) ?? {};
    if (layers.contains('bb')) {
      final up = _series(ind['bbUp']), lw = _series(ind['bbLo']);
      final up0 = n - up.length;
      final path = Path();
      var started = false;
      for (var k = 0; k < up.length; k++) {
        if (up[k] == null) continue;
        final p = Offset(xOfIdx((k + up0).toDouble()), yOf(up[k]!));
        started ? path.lineTo(p.dx, p.dy) : path.moveTo(p.dx, p.dy);
        started = true;
      }
      for (var k = lw.length - 1; k >= 0; k--) {
        if (lw[k] == null) continue;
        path.lineTo(xOfIdx((k + up0).toDouble()), yOf(lw[k]!));
      }
      path.close();
      canvas.drawPath(path, Paint()..color = Colors.indigo.withOpacity(0.07));
      _line(canvas, up, n, xOfIdx, yOf, Colors.indigo.withOpacity(0.5), 1);
      _line(canvas, lw, n, xOfIdx, yOf, Colors.indigo.withOpacity(0.5), 1);
    }
    if (layers.contains('ema')) {
      _line(canvas, _series(ind['ema9']), n, xOfIdx, yOf, const Color(0xFF22D3EE), 1.1);
      _line(canvas, _series(ind['ema20']), n, xOfIdx, yOf, const Color(0xFF3B82F6), 1.4);
      _line(canvas, _series(ind['ema50']), n, xOfIdx, yOf, const Color(0xFFF59E0B), 1.4);
      _line(canvas, _series(ind['ema200']), n, xOfIdx, yOf, const Color(0xFF8B5CF6), 1.6);
    }
    if (layers.contains('vwap')) {
      _line(canvas, _series(ind['vwap']), n, xOfIdx, yOf, Colors.teal, 1.3, dashed: true);
    }
    // ---- candles
    for (var k = 0; k < n; k++) {
      final c = candles[k];
      final o = d(c[1]), h = d(c[2]), l = d(c[3]), cl = d(c[4]);
      final up = cl >= o;
      final col = up ? (dark ? const Color(0xFF34D399) : Palette.green) : (dark ? const Color(0xFFF87171) : Palette.red);
      final x = xOfIdx(k.toDouble());
      canvas.drawLine(Offset(x, yOf(h)), Offset(x, yOf(l)), Paint()..color = col..strokeWidth = 1.2);
      final top = yOf(math.max(o, cl)), bot = yOf(math.min(o, cl));
      canvas.drawRect(Rect.fromLTRB(x - cw * 0.34, top, x + cw * 0.34, math.max(bot, top + 1)), Paint()..color = col);
    }
    // ---- swings
    if (layers.contains('swings')) {
      for (final s in (data['swings'] as List? ?? [])) {
        final x = xOfT(d(s['t'])), hi2 = s['kind'] == 'high';
        final y = yOf(d(s['p'])) + (hi2 ? -7 : 7);
        final p = Path();
        if (hi2) {
          p..moveTo(x, y + 4)..lineTo(x - 3.5, y - 2)..lineTo(x + 3.5, y - 2);
        } else {
          p..moveTo(x, y - 4)..lineTo(x - 3.5, y + 2)..lineTo(x + 3.5, y + 2);
        }
        canvas.drawPath(p..close(), Paint()..color = fg.withOpacity(0.6));
      }
    }
    // ---- trendlines (bold)
    if (layers.contains('trend')) {
      for (final t in (data['trendlines'] as List? ?? [])) {
        final sup = t['kind'] == 'support';
        final col = sup ? const Color(0xFF10B981) : const Color(0xFFEF4444);
        final p1 = d(t['p1']), p2 = d(t['p2']);
        final room = math.max(hi - lo, 1e-9);
        if (p1 < lo - room || p1 > hi + room || p2 < lo - room || p2 > hi + room) continue;
        final a = Offset(xOfT(d(t['t1'])), yOf(p1)), b = Offset(xOfT(d(t['t2'])), yOf(p2));
        final dir = b - a;
        final ext = b + dir / math.max(dir.dx, 1) * (cw * 4);
        canvas.drawLine(a, Offset(ext.dx.clamp(0, chartW), ext.dy.clamp(topPad, topPad + chartH)), Paint()..color = col..strokeWidth = 2.8..strokeCap = StrokeCap.round);
        canvas.drawCircle(a, 4, Paint()..color = col);
        _text(canvas, sup ? 'Trendline ↗ ${t['touches']}x' : 'Trendline ↘ ${t['touches']}x', b + const Offset(-70, -14), col, 10, bold: true);
      }
    }
    if (layers.contains('pivots')) {
      for (final pv in (data['pivots'] as List? ?? [])) {
        final col = pv['kind'] == 'support' ? Palette.green : (pv['kind'] == 'resistance' ? Palette.red : Palette.brand);
        _hline(canvas, yOf(d(pv['price'])), chartW, col.withOpacity(0.85), pv['label'].toString(), dashed: true, width: 1.0);
      }
    }
    if (layers.contains('session')) {
      for (final s in (data['sessions'] as List? ?? [])) {
        _hline(canvas, yOf(d(s['high'])), chartW, const Color(0xFF6366F1), '${s['session']} high', dashed: true, width: 1.0);
        _hline(canvas, yOf(d(s['low'])), chartW, const Color(0xFF6366F1), '${s['session']} low', dashed: true, width: 1.0);
      }
    }
    if (layers.contains('liq')) {
      for (final lq in (data['liquidity'] as List? ?? [])) {
        final eqh = lq['kind'] == 'eqh';
        _hline(canvas, yOf(d(lq['price'])), chartW, eqh ? Palette.gold : Palette.blue,
            eqh ? 'EQH liq ${lq['touches']}x' : 'EQL liq ${lq['touches']}x', dashed: true, width: 1.1);
      }
    }
    // ---- markers
    for (final m in (data['markers'] as List? ?? [])) {
      final p = Offset(xOfT(d(m['t'])), yOf(d(m['p'])));
      canvas.drawCircle(p, 6, Paint()..color = Palette.gold.withOpacity(0.35));
      _text(canvas, m['label'].toString(), p + const Offset(-60, -24), Palette.gold, 10, bold: true);
    }
    // ---- positions + plan
    for (final p in (data['positions'] as List? ?? [])) {
      _hline(canvas, yOf(d(p['entry'])), chartW, Palette.blue, 'POS ${p['side']} ${money(p['profit'], sign: true)}', dashed: false, width: 1.6);
      if (d(p['sl']) > 0) _hline(canvas, yOf(d(p['sl'])), chartW, Palette.red, 'SL', dashed: true);
      if (d(p['tp']) > 0) _hline(canvas, yOf(d(p['tp'])), chartW, Palette.green, 'TP', dashed: true);
    }
    if (layers.contains('plan') && plan is Map) {
      final live = (data['positions'] as List? ?? []).isNotEmpty;
      if (!live) {
        final tag = plan['tradable'] == true ? 'PLAN' : 'IDEA';
        _hline(canvas, yOf(d(plan['entry'])), chartW, Palette.blue, '$tag ${plan['side']} entry', dashed: true, width: 1.4);
        _hline(canvas, yOf(d(plan['sl'])), chartW, Palette.red, 'SL ${price(plan['sl'], digits)}', dashed: true, width: 1.4);
        _hline(canvas, yOf(d(plan['tp'])), chartW, Palette.green, 'TP ${price(plan['tp'], digits)}  R:R ${plan['rr']}', dashed: true, width: 1.4);
        final r1 = Rect.fromLTRB(chartW - 90, math.min(yOf(d(plan['entry'])), yOf(d(plan['tp']))), chartW, math.max(yOf(d(plan['entry'])), yOf(d(plan['tp']))));
        canvas.drawRect(r1, Paint()..color = Palette.green.withOpacity(0.08));
        final r2 = Rect.fromLTRB(chartW - 90, math.min(yOf(d(plan['entry'])), yOf(d(plan['sl']))), chartW, math.max(yOf(d(plan['entry'])), yOf(d(plan['sl']))));
        canvas.drawRect(r2, Paint()..color = Palette.red.withOpacity(0.08));
      }
    }
    // ---- last price
    final last = d(candles.last[4]);
    canvas.drawLine(Offset(0, yOf(last)), Offset(chartW, yOf(last)), Paint()..color = fg.withOpacity(0.45)..strokeWidth = 0.8);
    canvas.restore();
    final tagRect = Rect.fromLTWH(chartW + 1, yOf(last) - 9, rightPad - 2, 18);
    canvas.drawRRect(RRect.fromRectAndRadius(tagRect, const Radius.circular(4)), Paint()..color = Palette.brand);
    _text(canvas, last.toStringAsFixed(digits), Offset(chartW + 4, yOf(last) - 6), Colors.white, 10, bold: true);

    // ---- crosshair
    if (cursor != null && cursor!.dx < chartW && cursor!.dy > topPad && cursor!.dy < topPad + chartH) {
      final idx = (start + cursor!.dx / cw).round().clamp(0, n - 1);
      final c = candles[idx];
      final cp = Paint()..color = fg.withOpacity(0.5)..strokeWidth = 0.8;
      canvas.drawLine(Offset(xOfIdx(idx.toDouble()), topPad), Offset(xOfIdx(idx.toDouble()), topPad + chartH), cp);
      canvas.drawLine(Offset(0, cursor!.dy), Offset(chartW, cursor!.dy), cp);
      final pr = hi - (cursor!.dy - topPad) / chartH * (hi - lo);
      _text(canvas, pr.toStringAsFixed(digits), Offset(chartW + 4, cursor!.dy - 6), fg, 10, bold: true);
      final info = 'O ${price(c[1], digits)}  H ${price(c[2], digits)}  L ${price(c[3], digits)}  C ${price(c[4], digits)}  ${fmtDateTime(c[0])}';
      final tp = TextPainter(text: TextSpan(text: info, style: TextStyle(color: fg, fontSize: 10.5, fontWeight: FontWeight.w600)), textDirection: TextDirection.ltr)..layout();
      canvas.drawRRect(RRect.fromRectAndRadius(Rect.fromLTWH(6, 6, tp.width + 12, tp.height + 8), const Radius.circular(6)), Paint()..color = (dark ? Colors.black : Colors.white).withOpacity(0.8));
      tp.paint(canvas, const Offset(12, 10));
    }
    canvas.restore();
  }

  List<double?> _series(dynamic raw) => ((raw as List?) ?? []).map<double?>((e) => e == null ? null : d(e)).toList();

  void _line(Canvas canvas, List<double?> s, int n, double Function(double) xf, double Function(double) yf, Color c, double w, {bool dashed = false}) {
    final off = n - s.length;
    Offset? prev;
    final paint = Paint()..color = c..strokeWidth = w..style = PaintingStyle.stroke;
    for (var k = 0; k < s.length; k++) {
      if (s[k] == null) {
        prev = null;
        continue;
      }
      final p = Offset(xf((k + off).toDouble()), yf(s[k]!));
      if (prev != null && !(dashed && k % 4 == 0)) canvas.drawLine(prev, p, paint);
      prev = p;
    }
  }

  void _hline(Canvas canvas, double y, double w, Color c, String label, {bool dashed = true, double width = 1.2}) {
    final paint = Paint()..color = c..strokeWidth = width;
    if (!dashed) {
      canvas.drawLine(Offset(0, y), Offset(w, y), paint);
    } else {
      for (double x = 0; x < w; x += 9) {
        canvas.drawLine(Offset(x, y), Offset(math.min(x + 5, w), y), paint);
      }
    }
    final tp = TextPainter(text: TextSpan(text: label, style: const TextStyle(color: Colors.white, fontSize: 9.5, fontWeight: FontWeight.w800)), textDirection: TextDirection.ltr)..layout();
    final r = Rect.fromLTWH(w - tp.width - 12, y - tp.height - 3, tp.width + 8, tp.height + 3);
    canvas.drawRRect(RRect.fromRectAndRadius(r, const Radius.circular(4)), Paint()..color = c);
    tp.paint(canvas, Offset(r.left + 4, r.top + 1));
  }

  void _text(Canvas canvas, String s, Offset o, Color c, double size, {bool bold = false}) {
    final tp = TextPainter(text: TextSpan(text: s, style: TextStyle(color: c, fontSize: size, fontWeight: bold ? FontWeight.w800 : FontWeight.w500)), textDirection: TextDirection.ltr)..layout();
    tp.paint(canvas, o);
  }

  @override
  bool shouldRepaint(covariant CandlePainter old) => true;
}
