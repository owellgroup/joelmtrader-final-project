import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/app_state.dart';
import '../core/utils.dart';
import '../widgets/common.dart';
import 'admins_page.dart';
import 'charts_page.dart';
import 'dashboard_page.dart';
import 'news_page.dart';
import 'notifications_page.dart';
import 'positions_page.dart';
import 'reports_page.dart';
import 'settings_page.dart';
import 'transactions_page.dart';

class _Item {
  final String label;
  final IconData icon;
  final Widget Function() build;
  const _Item(this.label, this.icon, this.build);
}

class Shell extends StatefulWidget {
  const Shell({super.key});
  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  int _index = 0;
  final _scaffold = GlobalKey<ScaffoldState>();
  Timer? _timer;
  String _status = 'STOPPED';
  bool _engineOnline = true;

  late final List<_Item> _items = [
    _Item('Dashboard', Icons.dashboard_rounded, () => const DashboardPage()),
    _Item('Alerts', Icons.notifications_rounded, () => const NotificationsPage()),
    _Item('Charts & Analysis', Icons.candlestick_chart_rounded, () => const ChartsPage()),
    _Item('Trades', Icons.swap_vert_circle_rounded, () => const PositionsPage()),
    _Item('Transactions', Icons.receipt_long_rounded, () => const TransactionsPage()),
    _Item('Reports', Icons.insights_rounded, () => const ReportsPage()),
    _Item('Market News', Icons.newspaper_rounded, () => const NewsPage()),
    _Item('Admins', Icons.admin_panel_settings_rounded, () => const AdminsPage()),
    _Item('Settings', Icons.settings_rounded, () => const SettingsPage()),
  ];

  @override
  void initState() {
    super.initState();
    _poll();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _poll());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _poll() async {
    try {
      final r = await context.read<AppState>().api.get('/api/bot/status');
      if (!mounted) return;
      setState(() {
        _engineOnline = r['engineOnline'] == true;
        _status = r['running'] == true ? (r['engine']?['status']?.toString() ?? 'RUNNING') : 'STOPPED';
      });
    } catch (_) {
      if (mounted) setState(() => _engineOnline = false);
    }
  }

  Color _statusColor() {
    if (!_engineOnline) return Palette.red;
    switch (_status) {
      case 'STOPPED':
        return Palette.slate;
      case 'HALTED':
      case 'DISCONNECTED':
        return Palette.red;
      case 'COOLDOWN':
        return Palette.gold;
      default:
        return Palette.green;
    }
  }

  Widget _nav(bool inDrawer) {
    final s = context.watch<AppState>();
    final visible = [for (var k = 0; k < _items.length; k++) k];
    return Container(
      width: 270,
      color: context.isDark ? const Color(0xFF0C1020) : Colors.white,
      child: SafeArea(
        child: Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(2, 16, 12, 12),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Transform.translate(offset: const Offset(-8, 0), child: const BrandLogo(height: 64)),
              const SizedBox(height: 8),
              Text('TRADING DESK', style: TextStyle(fontSize: 11, color: Palette.brand, fontWeight: FontWeight.w800, letterSpacing: 1.6)),
            ]),
          ),
          Expanded(
            child: ListView(padding: const EdgeInsets.symmetric(horizontal: 12), children: [
              for (final k in visible)
                _NavTile(
                  item: _items[k],
                  selected: _index == k,
                  onTap: () {
                    setState(() => _index = k);
                    if (inDrawer) Navigator.pop(context);
                  },
                ),
            ]),
          ),
          Padding(
            padding: const EdgeInsets.all(14),
            child: AppCard(
              padding: const EdgeInsets.all(12),
              child: Row(children: [
                CircleAvatar(radius: 16, backgroundColor: Palette.brand.withOpacity(0.15), child: const Icon(Icons.person, size: 18, color: Palette.brand)),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(s.user?['username']?.toString() ?? '', maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12.5)),
                    Text(s.isSuper ? 'Super admin' : 'Admin', style: TextStyle(fontSize: 11, color: context.muted)),
                  ]),
                ),
                IconButton(
                  tooltip: 'Log out',
                  icon: const Icon(Icons.logout_rounded, size: 20),
                  onPressed: () async {
                    if (await confirmDialog(context, 'Log out?', 'You will need to sign in again on this device.', confirm: 'Log out')) {
                      if (inDrawer && mounted) Navigator.pop(context);
                      await s.logout();
                    }
                  },
                ),
              ]),
            ),
          ),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = context.watch<AppState>();
    return LayoutBuilder(builder: (context, c) {
      final wide = c.maxWidth >= 960;
      return Scaffold(
        key: _scaffold,
        drawer: wide ? null : Drawer(width: 270, child: _nav(true)),
        appBar: AppBar(
          automaticallyImplyLeading: false,
          leading: wide ? null : IconButton(icon: const Icon(Icons.menu_rounded), onPressed: () => _scaffold.currentState?.openDrawer()),
          title: Text(_items[_index].label, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w800)),
          actions: [
            IconButton(
              tooltip: 'Alerts',
              onPressed: () => setState(() => _index = 1),
              icon: Badge(
                isLabelVisible: s.unreadAlerts > 0,
                label: Text('${s.unreadAlerts > 99 ? '99+' : s.unreadAlerts}'),
                child: const Icon(Icons.notifications_rounded),
              ),
            ),
            if (wide)
              Padding(
                padding: const EdgeInsets.only(right: 6),
                child: Center(child: StatusPill(!_engineOnline ? 'ENGINE OFFLINE' : _status, _statusColor(), pulse: _status != 'STOPPED' && _engineOnline)),
              ),
            IconButton(
              tooltip: 'Toggle theme',
              icon: AnimatedSwitcher(duration: const Duration(milliseconds: 300), child: Icon(context.isDark ? Icons.light_mode_rounded : Icons.dark_mode_rounded, key: ValueKey(context.isDark))),
              onPressed: s.toggleTheme,
            ),
            const SizedBox(width: 6),
          ],
        ),
        body: Row(children: [
          if (wide) _nav(false),
          if (wide) VerticalDivider(width: 1, color: context.borderColor),
          Expanded(
            child: Column(children: [
              if (!wide)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  color: context.isDark ? const Color(0xFF12182B) : const Color(0xFFE7EBFF),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: StatusPill(!_engineOnline ? 'ENGINE OFFLINE' : _status, _statusColor(), pulse: _status != 'STOPPED' && _engineOnline),
                  ),
                ),
              if (s.offlineWarning) Container(width: double.infinity, color: Palette.gold.withOpacity(0.2), padding: const EdgeInsets.all(8), child: const Text('Server unreachable - showing cached login. Check your connection.', textAlign: TextAlign.center, style: TextStyle(fontSize: 12))),
              Expanded(
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 280),
                  transitionBuilder: (child, anim) => FadeTransition(opacity: anim, child: SlideTransition(position: Tween(begin: const Offset(0, 0.015), end: Offset.zero).animate(anim), child: child)),
                  child: KeyedSubtree(key: ValueKey(_index), child: _items[_index].build()),
                ),
              ),
            ]),
          ),
        ]),
      );
    });
  }
}

class _NavTile extends StatelessWidget {
  final _Item item;
  final bool selected;
  final VoidCallback onTap;
  const _NavTile({required this.item, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        decoration: BoxDecoration(
          color: selected ? Palette.brand.withOpacity(0.13) : Colors.transparent,
          borderRadius: BorderRadius.circular(14),
        ),
        child: ListTile(
          dense: true,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          leading: Icon(item.icon, color: selected ? Palette.brand : context.muted),
          title: Text(item.label, style: TextStyle(fontWeight: selected ? FontWeight.w800 : FontWeight.w600, color: selected ? Palette.brand : context.textColor)),
          onTap: onTap,
        ),
      ),
    );
  }
}
