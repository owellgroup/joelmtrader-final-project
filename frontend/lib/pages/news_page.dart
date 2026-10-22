import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/api.dart';
import '../core/app_state.dart';
import '../core/utils.dart';
import '../widgets/common.dart';

class NewsPage extends StatefulWidget {
  const NewsPage({super.key});
  @override
  State<NewsPage> createState() => _NewsPageState();
}

class _NewsPageState extends State<NewsPage> {
  Map<String, dynamic>? _data;
  String? _error;
  String _filter = 'ALL';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await context.read<AppState>().api.get('/api/market/news');
      if (mounted) setState(() {
        _data = Map<String, dynamic>.from(r);
        _error = null;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    if (data == null) return Center(child: _error != null ? ErrorBanner(_error!, onRetry: _load) : const CircularProgressIndicator(color: Palette.brand));
    final events = (data['events'] as List?) ?? [];
    final heads = ((data['headlines'] as List?) ?? []).where((h) => _filter == 'ALL' || (h['symbols'] as List).contains(_filter)).toList();
    final blocked = Map<String, dynamic>.from(data['blocked'] ?? {});
    final now = DateTime.now().millisecondsSinceEpoch / 1000;
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(padding: const EdgeInsets.all(16), children: [
        ResponsiveGrid(minTileWidth: 260, children: [
          for (final e in blocked.entries)
            AppCard(
              child: Row(children: [
                Icon(e.value['blocked'] == true ? Icons.pause_circle_filled_rounded : Icons.check_circle_rounded, color: e.value['blocked'] == true ? Palette.red : Palette.green),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(e.key, style: const TextStyle(fontWeight: FontWeight.w900)),
                    Text(e.value['blocked'] == true ? e.value['reason'].toString() : 'Clear to trade', style: TextStyle(fontSize: 11.5, color: context.muted)),
                  ]),
                ),
              ]),
            ),
        ]),
        const SizedBox(height: 16),
        AppCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const SectionTitle('Economic calendar', subtitle: 'High-impact USD / EUR / GBP events (your local time)'),
            if (events.isEmpty) Text('Calendar unavailable or no events.', style: TextStyle(color: context.muted)),
            for (final e in events)
              Opacity(
                opacity: d(e['time']) < now ? 0.5 : 1,
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Wrap(spacing: 6, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
                      Text(fmtDateTime(e['time']), style: TextStyle(fontSize: 11.5, color: context.muted)),
                      Tag(e['currency'].toString(), Palette.blue),
                      Tag(e['impact'] == 'High' ? 'HIGH' : 'MED', e['impact'] == 'High' ? Palette.red : Palette.gold),
                      if ((e['forecast'] ?? '').toString().isNotEmpty) Text('F ${e['forecast']}', style: TextStyle(fontSize: 11, color: context.muted)),
                    ]),
                    const SizedBox(height: 4),
                    Text(e['title'].toString(), style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, height: 1.3)),
                  ]),
                ),
              ),
          ]),
        ),
        const SizedBox(height: 16),
        AppCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const SectionTitle('Market headlines', subtitle: 'Filter by the pair you want to read'),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final f in ['ALL', 'XAUUSD', 'GBPJPY', 'EURJPY', 'EURUSD', 'GBPUSD'])
                SelectChip(
                  label: f,
                  selected: _filter == f,
                  onSelected: () => setState(() => _filter = f),
                ),
            ]),
            const SizedBox(height: 8),
            if (heads.isEmpty) Text('No headlines.', style: TextStyle(color: context.muted)),
            for (final h in heads)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(h['title'].toString(), style: const TextStyle(fontWeight: FontWeight.w600, height: 1.35)),
                  const SizedBox(height: 4),
                  Wrap(spacing: 6, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
                    Text('${h['source']} · ${fmtDateTime(h['time'])}', style: TextStyle(fontSize: 11, color: context.muted)),
                    for (final s in (h['symbols'] as List)) Tag(s.toString().substring(0, 3), Palette.brand),
                  ]),
                ]),
              ),
          ]),
        ),
      ]),
    );
  }
}
