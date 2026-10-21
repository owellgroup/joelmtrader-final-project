import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/api.dart';
import '../core/app_state.dart';
import '../core/utils.dart';
import '../widgets/common.dart';

class TransactionsPage extends StatefulWidget {
  const TransactionsPage({super.key});
  @override
  State<TransactionsPage> createState() => _TransactionsPageState();
}

class _TransactionsPageState extends State<TransactionsPage> {
  final List _items = [];
  int _page = 0, _totalPages = 1;
  bool _loading = false;
  String? _type, _error;
  static const types = {null: 'All', 'TRADE_OPEN': 'Opens', 'TRADE_CLOSE': 'Closes', 'BOT_START': 'Starts', 'BOT_STOP': 'Stops', 'HALT': 'Halts'};

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
  }

  Future<void> _more() async {
    if (_loading || _page >= _totalPages) return;
    setState(() => _loading = true);
    try {
      final r = await context.read<AppState>().api.get('/api/transactions', query: {'page': _page, 'size': 40, if (_type != null) 'type': _type});
      if (mounted) setState(() {
        _items.addAll(r['items'] as List);
        _totalPages = i(r['totalPages'], 1);
        _page++;
        _error = null;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  (IconData, Color) _style(String t, dynamic amount) {
    switch (t) {
      case 'TRADE_OPEN':
        return (Icons.north_east_rounded, Palette.blue);
      case 'TRADE_CLOSE':
        return (d(amount) >= 0 ? Icons.check_circle_rounded : Icons.cancel_rounded, d(amount) >= 0 ? Palette.green : Palette.red);
      case 'BOT_START':
        return (Icons.play_circle_rounded, Palette.brand);
      case 'BOT_STOP':
        return (Icons.stop_circle_rounded, Palette.slate);
      case 'HALT':
        return (Icons.warning_rounded, Palette.red);
      default:
        return (Icons.circle, Palette.slate);
    }
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView(padding: const EdgeInsets.all(16), children: [
        const SectionTitle('Transaction ledger', subtitle: 'Every open, close and bot event with opening / closing balance'),
        Wrap(spacing: 8, children: [
          for (final e in types.entries)
            SelectChip(label: e.value, selected: _type == e.key, onSelected: () {
              setState(() => _type = e.key);
              _reload();
            }),
        ]),
        const SizedBox(height: 12),
        if (_error != null) ErrorBanner(_error!, onRetry: _reload),
        if (_items.isEmpty && !_loading && _error == null) const EmptyState(icon: Icons.receipt_long_rounded, title: 'No transactions yet'),
        AppCard(
          padding: EdgeInsets.zero,
          child: Column(children: [
            for (var k = 0; k < _items.length; k++) ...[
              _row(context, Map<String, dynamic>.from(_items[k])),
              if (k < _items.length - 1) Divider(height: 1, color: context.borderColor),
            ],
          ]),
        ),
        if (_page < _totalPages) Padding(padding: const EdgeInsets.all(16), child: Center(child: _loading ? const CircularProgressIndicator(color: Palette.brand) : Pressable(onPressed: _more, background: Colors.transparent, side: const BorderSide(color: Palette.brand), child: const Text('Load more')))),
      ]),
    );
  }

  Widget _row(BuildContext context, Map<String, dynamic> t) {
    final (icon, col) = _style(t['type'].toString(), t['amount']);
    final isClose = t['type'] == 'TRADE_CLOSE';
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icon, color: col),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Wrap(spacing: 8, runSpacing: 2, crossAxisAlignment: WrapCrossAlignment.center, children: [
              Text(t['type'].toString().replaceAll('_', ' '), style: TextStyle(fontWeight: FontWeight.w800, fontSize: 12, color: col)),
              if (t['symbol'] != null) Text(t['symbol'].toString(), style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 12)),
              Text(fmtDateTime(t['time']), style: TextStyle(fontSize: 11, color: context.muted)),
            ]),
            const SizedBox(height: 3),
            Text(t['remark']?.toString() ?? '', style: const TextStyle(fontSize: 12.5, height: 1.3)),
            if (t['balanceBefore'] != null || t['balanceAfter'] != null)
              Padding(
                padding: const EdgeInsets.only(top: 3),
                child: Text('Balance ${t['balanceBefore'] != null ? money(t['balanceBefore']) : '-'} → ${t['balanceAfter'] != null ? money(t['balanceAfter']) : '-'}', style: TextStyle(fontSize: 11, color: context.muted)),
              ),
          ]),
        ),
        if (isClose) Padding(padding: const EdgeInsets.only(left: 10), child: Text(money(t['amount'], sign: true), style: TextStyle(fontWeight: FontWeight.w900, color: context.pnl(t['amount'])))),
      ]),
    );
  }
}
