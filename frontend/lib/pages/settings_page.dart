import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/api.dart';
import '../core/app_state.dart';
import '../core/utils.dart';
import '../widgets/common.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});
  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  final _login = TextEditingController();
  final _server = TextEditingController();
  final _password = TextEditingController();
  late final TextEditingController _url;
  Map<String, dynamic>? _mt5;
  Map<String, dynamic>? _risk;
  String? _error;
  bool _busyMt5 = false, _busyRisk = false, _hide = true;

  Api get api => context.read<AppState>().api;

  @override
  void initState() {
    super.initState();
    _url = TextEditingController(text: context.read<AppState>().apiUrl);
    _load();
  }

  Future<void> _load() async {
    try {
      final m = await api.get('/api/settings/mt5');
      final r = await api.get('/api/settings/risk');
      if (!mounted) return;
      setState(() {
        _mt5 = Map<String, dynamic>.from(m);
        _risk = Map<String, dynamic>.from(r);
        if (_login.text.isEmpty) _login.text = m['login']?.toString() ?? '';
        if (_server.text.isEmpty) _server.text = m['server']?.toString() ?? '';
        _error = null;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  Future<void> _saveMt5() async {
    setState(() => _busyMt5 = true);
    try {
      final r = await api.put('/api/settings/mt5', body: {'login': _login.text.trim(), 'server': _server.text.trim(), 'password': _password.text});
      _password.clear();
      final res = r['connectResult'];
      if (mounted) {
        setState(() => _mt5 = Map<String, dynamic>.from(r));
        context.toast(res != null && res['connected'] == true ? 'Connected to MT5' : 'Saved, but not connected: ${res?['message'] ?? ''}', error: !(res != null && res['connected'] == true));
      }
    } on ApiException catch (e) {
      if (mounted) context.toast(e.message, error: true);
    } finally {
      if (mounted) setState(() => _busyMt5 = false);
    }
  }

  Future<void> _reconnect() async {
    setState(() => _busyMt5 = true);
    try {
      final r = await api.post('/api/settings/mt5/connect');
      if (mounted) context.toast(r['connected'] == true ? 'Connected to MT5' : (r['message']?.toString() ?? 'Not connected'), error: r['connected'] != true);
      await _load();
    } on ApiException catch (e) {
      if (mounted) context.toast(e.message, error: true);
    } finally {
      if (mounted) setState(() => _busyMt5 = false);
    }
  }

  Future<void> _saveRisk() async {
    setState(() => _busyRisk = true);
    try {
      final r = await api.put('/api/settings/risk', body: _risk);
      if (mounted) {
        setState(() => _risk = Map<String, dynamic>.from(r));
        context.toast('Risk settings saved');
      }
    } on ApiException catch (e) {
      if (mounted) context.toast(e.message, error: true);
    } finally {
      if (mounted) setState(() => _busyRisk = false);
    }
  }

  Widget _slider(String key, String label, double min, double max, {int? divisions, String suffix = '', String? help}) {
    final v = d(_risk![key]).clamp(min, max).toDouble();
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(label, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13))),
          Text('${v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(1)}$suffix', style: const TextStyle(fontWeight: FontWeight.w900, color: Palette.brand)),
        ]),
        Slider(value: v, min: min, max: max, divisions: divisions, onChanged: (x) => setState(() => _risk![key] = x)),
        if (help != null) Text(help, style: TextStyle(fontSize: 11, color: context.muted)),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final st = Map<String, dynamic>.from(_mt5?['status'] ?? {});
    final connected = st['connected'] == true;
    return ListView(padding: const EdgeInsets.all(16), children: [
      if (_error != null) Padding(padding: const EdgeInsets.only(bottom: 12), child: ErrorBanner(_error!, onRetry: _load)),
      // ---------------- appearance
      AppCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SectionTitle('Appearance'),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: SegmentedButton<ThemeMode>(
              segments: const [
                ButtonSegment(value: ThemeMode.light, label: Text('White'), icon: Icon(Icons.light_mode_rounded)),
                ButtonSegment(value: ThemeMode.dark, label: Text('Black'), icon: Icon(Icons.dark_mode_rounded)),
                ButtonSegment(value: ThemeMode.system, label: Text('System'), icon: Icon(Icons.brightness_auto_rounded)),
              ],
              selected: {app.themeMode},
              onSelectionChanged: (s) => app.setTheme(s.first),
            ),
          ),
        ]),
      ),
      const SizedBox(height: 16),
      // ---------------- MT5
      AppCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SectionTitle('Broker account (MetaTrader 5)', subtitle: 'Link the MT5 account the bot should trade', trailing: StatusPill(connected ? 'CONNECTED' : 'NOT CONNECTED', connected ? Palette.green : Palette.red)),
          if (st['mode'] == 'paper')
            Container(
              margin: const EdgeInsets.only(bottom: 12),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(color: Palette.gold.withOpacity(0.12), borderRadius: BorderRadius.circular(12)),
              child: const Text('The engine is running in PAPER mode (built-in simulator, no real orders). Set BROKER_MODE=mt5 in the backend .env to trade a real or demo MT5 account.', style: TextStyle(fontSize: 12.5, height: 1.4)),
            ),
          if (connected)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Wrap(spacing: 8, runSpacing: 6, children: [
                Tag('Login ${st['login']}', Palette.brand),
                Tag('${st['server']}', Palette.blue),
                if (st['demo'] == true) const Tag('DEMO', Palette.gold) else if (st['mode'] == 'mt5') const Tag('LIVE', Palette.red),
                if (st['leverage'] != null) Tag('1:${st['leverage']}', Palette.slate),
                if (st['trade_allowed'] == false) const Tag('TRADING DISABLED IN TERMINAL', Palette.red),
              ]),
            )
          else if ((st['message'] ?? '').toString().isNotEmpty)
            Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(st['message'].toString(), style: const TextStyle(color: Palette.red, fontSize: 12.5))),
          ResponsiveGrid(minTileWidth: 240, children: [
            TextField(controller: _login, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'MT5 login (account number)')),
            TextField(controller: _server, decoration: const InputDecoration(labelText: 'Broker server', hintText: 'e.g. Exness-MT5Real8')),
            TextField(
              controller: _password,
              obscureText: _hide,
              decoration: InputDecoration(
                labelText: _mt5?['hasPassword'] == true ? 'Password (saved - leave empty to keep)' : 'MT5 password',
                suffixIcon: IconButton(icon: Icon(_hide ? Icons.visibility_off_outlined : Icons.visibility_outlined), onPressed: () => setState(() => _hide = !_hide)),
              ),
            ),
          ]),
          const SizedBox(height: 14),
          Wrap(spacing: 10, runSpacing: 10, children: [
            Pressable(onPressed: (_busyMt5 || !app.isSuper) ? null : _saveMt5, background: Palette.brand, foreground: Colors.white, icon: _busyMt5 ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Icon(Icons.link_rounded), child: const Text('Save & connect')),
            Pressable(onPressed: _busyMt5 ? null : _reconnect, background: Colors.transparent, side: const BorderSide(color: Palette.brand), icon: const Icon(Icons.refresh_rounded), child: const Text('Reconnect')),
          ]),
          const SizedBox(height: 8),
          Text('The password is stored encrypted (AES-256) on your server and only used to log the MT5 terminal in. Use your trading password, not the investor password. Start with a DEMO account.', style: TextStyle(fontSize: 11.5, color: context.muted, height: 1.4)),
        ]),
      ),
      const SizedBox(height: 16),
      // ---------------- risk
      AppCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SectionTitle('Risk management', subtitle: 'Applied by the engine before every trade'),
          if (_risk == null)
            const Padding(padding: EdgeInsets.all(12), child: Text('Loading...'))
          else ...[
            _slider('risk_per_trade_pct', 'Risk per trade', 0.5, 5, divisions: 9, suffix: '%', help: 'Share of equity lost if the stop-loss is hit.'),
            _slider('micro_max_risk_pct', 'Micro-account hard cap per trade', 2, 15, divisions: 13, suffix: '%', help: 'With tiny balances the broker minimum lot can exceed your risk %. The bot only takes it if risk stays below this cap - otherwise it skips.'),
            _slider('max_total_open_risk_pct', 'Max total open risk', 2, 20, divisions: 18, suffix: '%'),
            _slider('max_positions', 'Max simultaneous positions', 1, 6, divisions: 5),
            _slider('max_same_usd_direction', 'Max trades betting the same way on USD', 1, 3, divisions: 2, help: 'Gold, EURUSD and GBPUSD all move against the dollar.'),
            _slider('max_same_jpy_direction', 'Max trades betting the same way on JPY', 1, 2, divisions: 1, help: 'GBPJPY and EURJPY are closely correlated.'),
            _slider('daily_loss_limit_pct', 'Daily loss limit (pauses until next day)', 2, 20, divisions: 18, suffix: '%'),
            _slider('max_drawdown_pct', 'Max drawdown kill-switch', 5, 50, divisions: 45, suffix: '%'),
            _slider('max_consecutive_losses', 'Losses in a row before cooldown', 1, 6, divisions: 5),
            _slider('cooldown_minutes', 'Cooldown length', 5, 120, divisions: 23, suffix: ' min'),
            _slider('min_score', 'Minimum opportunity score', 50, 90, divisions: 40, help: 'Higher = fewer but better trades.'),
            _slider('min_rr', 'Minimum reward : risk', 1, 3, divisions: 20),
            _slider('max_trade_minutes', 'Time stop (no follow-through)', 10, 180, divisions: 17, suffix: ' min'),
            _slider('trade_start_utc', 'Trading window start (UTC hour)', 0, 23, divisions: 23),
            _slider('trade_end_utc', 'Trading window end (UTC hour)', 1, 24, divisions: 23),
            ToggleLine(title: 'Close trades before high-impact news', value: _risk!['close_before_news'] == true, onChanged: (v) => setState(() => _risk!['close_before_news'] = v)),
            const SizedBox(height: 4),
            Wrap(spacing: 8, children: [
              for (final s in ['XAUUSD', 'GBPJPY', 'EURJPY', 'EURUSD', 'GBPUSD'])
                SelectChip(
                  label: s,
                  selected: ((_risk!['allowed_symbols'] as List?) ?? []).contains(s),
                  onSelected: () => setState(() {
                    final l = List<String>.from((_risk!['allowed_symbols'] as List?) ?? []);
                    ((_risk!['allowed_symbols'] as List?) ?? []).contains(s) ? l.remove(s) : l.add(s);
                    _risk!['allowed_symbols'] = l;
                  }),
                ),
            ]),
            const SizedBox(height: 14),
            Pressable(onPressed: (_busyRisk || !app.isSuper) ? null : _saveRisk, background: Palette.brand, foreground: Colors.white, icon: const Icon(Icons.save_rounded), child: const Text('Save risk settings')),
            if (!app.isSuper) Padding(padding: const EdgeInsets.only(top: 6), child: Text('Only the super admin can change these.', style: TextStyle(fontSize: 11.5, color: context.muted))),
          ],
        ]),
      ),
      const SizedBox(height: 16),
      // ---------------- connection / account
      AppCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SectionTitle('App connection'),
          TextField(
            controller: _url,
            enableInteractiveSelection: true,
            keyboardType: TextInputType.url,
            contextMenuBuilder: (context, state) => AdaptiveTextSelectionToolbar.editableText(editableTextState: state),
            decoration: const InputDecoration(labelText: 'Backend URL', prefixIcon: Icon(Icons.dns_outlined)),
          ),
          const SizedBox(height: 10),
          Wrap(spacing: 10, children: [
            Pressable(onPressed: () async {
              await app.setApiUrl(_url.text);
              if (mounted) context.toast('Server URL saved');
              _load();
            }, background: Colors.transparent, side: const BorderSide(color: Palette.brand), child: const Text('Save URL')),
            Pressable(onPressed: () async {
              try {
                final r = await api.post('/api/settings/test-email');
                if (!mounted) return;
                final sent = r is Map && r['sent'] == true;
                final delivered = r is Map ? r['delivered'] : null;
                final error = r is Map ? r['error']?.toString() : null;
                final msg = sent
                    ? 'Test push sent to $delivered phone${delivered == 1 ? '' : 's'}. It should pop up with the app closed.'
                    : (error ?? 'Push failed. Check the FCM settings on the server.');
                context.toast(msg, error: !sent);
              } on ApiException catch (e) {
                if (mounted) context.toast(e.message, error: true);
              }
            }, background: Colors.transparent, side: const BorderSide(color: Palette.brand), icon: const Icon(Icons.notifications_active_rounded), child: const Text('Send test push')),
          ]),
          const Divider(height: 30),
          LayoutBuilder(builder: (context, c) {
            final who = Row(children: [
              const Icon(Icons.person_rounded, color: Palette.brand),
              const SizedBox(width: 10),
              Expanded(child: Text('${app.user?['username']}  ·  ${app.isSuper ? 'Super admin' : 'Admin'}', maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700))),
            ]);
            final logout = Pressable(
              background: Palette.red,
              foreground: Colors.white,
              expand: c.maxWidth < 480,
              onPressed: () async {
                if (await confirmDialog(context, 'Log out?', 'You will need to sign in again on this device.', confirm: 'Log out')) app.logout();
              },
              icon: const Icon(Icons.logout_rounded),
              child: const Text('Log out'),
            );
            if (c.maxWidth < 480) {
              return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                who,
                const SizedBox(height: 12),
                logout,
              ]);
            }
            return Row(children: [Expanded(child: who), const SizedBox(width: 12), logout]);
          }),
        ]),
      ),
      const SizedBox(height: 24),
    ]);
  }
}
