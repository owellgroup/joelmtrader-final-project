import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'core/app_state.dart';
import 'core/push_bridge.dart';
import 'core/theme.dart';
import 'core/utils.dart';
import 'firebase_options.dart';
import 'pages/login_page.dart';
import 'pages/shell.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (!kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.android ||
          defaultTargetPlatform == TargetPlatform.iOS ||
          defaultTargetPlatform == TargetPlatform.macOS)) {
    try {
      await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
      FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
    } catch (_) {}
  }
  final state = AppState();
  await state.init();
  runApp(ChangeNotifierProvider.value(value: state, child: const WayaApp()));
}

class WayaApp extends StatefulWidget {
  const WayaApp({super.key});
  @override
  State<WayaApp> createState() => _WayaAppState();
}

class _WayaAppState extends State<WayaApp> {
  final _push = PushBridge();

  @override
  void initState() {
    super.initState();
    final state = context.read<AppState>();
    state.addListener(_syncPush);
    _syncPush();
  }

  void _syncPush() {
    final state = context.read<AppState>();
    if (state.loggedIn) {
      _push.start(state);
    } else {
      _push.stop();
    }
  }

  @override
  void dispose() {
    context.read<AppState>().removeListener(_syncPush);
    _push.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = context.watch<AppState>();
    return MaterialApp(
      title: 'JoelMTrader',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(Brightness.light),
      darkTheme: buildTheme(Brightness.dark),
      themeMode: s.themeMode,
      home: SelectionArea(
        child: AnimatedSwitcher(
          duration: const Duration(milliseconds: 400),
          child: !s.ready
              ? const Scaffold(body: Center(child: CircularProgressIndicator(color: Palette.brand)))
              : (s.loggedIn ? const Shell(key: ValueKey('shell')) : const LoginPage(key: ValueKey('login'))),
        ),
      ),
    );
  }
}
