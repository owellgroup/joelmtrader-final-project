import 'dart:async';

import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../firebase_options.dart';
import 'app_state.dart';

bool get _underTest => WidgetsBinding.instance.runtimeType.toString().contains('Test');

bool get _fcmPlatform {
  if (kIsWeb) return false;
  return defaultTargetPlatform == TargetPlatform.android || defaultTargetPlatform == TargetPlatform.iOS || defaultTargetPlatform == TargetPlatform.macOS;
}

@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  } catch (_) {}
}

/// Shows system pop-ups on Android, iOS, Windows, and Linux, and keeps the in-app badge current.
class PushBridge {
  final _local = FlutterLocalNotificationsPlugin();
  Timer? _timer;
  AppState? _state;
  bool _ready = false;
  int _lastShown = 0;
  final Set<int> _shown = {};

  void start(AppState state) {
    _state = state;
    if (_underTest) return;
    unawaited(_boot());
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
    _state = null;
  }

  Future<void> _boot() async {
    if (_ready) {
      _timer ??= Timer.periodic(const Duration(seconds: 4), (_) => _poll());
      return;
    }
    final prefs = await SharedPreferences.getInstance();
    _lastShown = prefs.getInt('pushLastId') ?? 0;
    await _initLocal();
    await _initFcm();
    _ready = true;
    await _poll();
    _timer ??= Timer.periodic(const Duration(seconds: 4), (_) => _poll());
  }

  Future<void> _initLocal() async {
    const android = AndroidInitializationSettings('@drawable/ic_stat_notify');
    const darwin = DarwinInitializationSettings(requestAlertPermission: true, requestBadgePermission: true, requestSoundPermission: true);
    const windows = WindowsInitializationSettings(
      appName: 'JoelMTrader',
      appUserModelId: 'WayaSpot.JoelMTrader',
      guid: 'c3a1e7b4-6d28-4f91-9a55-2b8e4d0c7f13',
    );
    final linux = LinuxInitializationSettings(
      defaultActionName: 'Open',
      defaultIcon: AssetsLinuxIcon('assets/images/icon.svg'),
    );
    try {
      await _local.initialize(settings: InitializationSettings(android: android, iOS: darwin, macOS: darwin, linux: linux, windows: windows));
    } catch (_) {
      await _local.initialize(settings: InitializationSettings(android: android, iOS: darwin, macOS: darwin, windows: windows, linux: const LinuxInitializationSettings(defaultActionName: 'Open')));
    }
    if (defaultTargetPlatform == TargetPlatform.android) {
      await _local.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()?.requestNotificationsPermission();
    }
  }

  Future<void> _initFcm() async {
    if (!_fcmPlatform) return;
    try {
      await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
      FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
      final messaging = FirebaseMessaging.instance;
      await messaging.requestPermission(alert: true, badge: true, sound: true, criticalAlert: true);
      await messaging.setForegroundNotificationPresentationOptions(alert: true, badge: true, sound: true);
      // getToken is the device token FCM HTTP v1 sends to. register()/onRegistered returns an installation id instead.
      // ignore: deprecated_member_use
      final token = await messaging.getToken();
      final state = _state;
      if (token != null && state != null) {
        await state.api.post('/api/devices', body: {'token': token, 'platform': defaultTargetPlatform.name});
      }
      FirebaseMessaging.onMessage.listen((message) {
        final id = int.tryParse(message.data['id'] ?? '') ?? message.hashCode;
        unawaited(show(
          id: id,
          title: message.notification?.title ?? 'JoelMTrader',
          body: message.notification?.body ?? '',
        ));
      });
    } catch (e) {
      debugPrint('Push setup skipped: $e');
    }
  }

  Future<void> _poll() async {
    final state = _state;
    if (state == null || !state.loggedIn) return;
    try {
      final raw = await state.api.get('/api/notifications');
      if (raw is! Map) return;
      final unread = raw['unread'];
      state.setUnreadAlerts(unread is num ? unread.toInt() : 0);
      final items = raw['items'];
      if (items is! List) return;
      final fresh = <Map<String, dynamic>>[];
      var maxId = _lastShown;
      for (final item in items) {
        if (item is! Map) continue;
        final row = Map<String, dynamic>.from(item);
        final id = row['id'];
        if (id is! num) continue;
        final n = id.toInt();
        if (n > maxId) maxId = n;
        if (n > _lastShown) fresh.add(row);
      }
      fresh.sort((a, b) => (a['id'] as num).compareTo(b['id'] as num));
      if (_lastShown == 0 && !(await SharedPreferences.getInstance()).containsKey('pushLastId')) {
        _lastShown = maxId;
        await (await SharedPreferences.getInstance()).setInt('pushLastId', maxId);
        return;
      }
      for (final row in fresh) {
        await show(id: (row['id'] as num).toInt(), title: '${row['title'] ?? 'JoelMTrader'}', body: '${row['body'] ?? ''}');
      }
      if (maxId > _lastShown) {
        _lastShown = maxId;
        await (await SharedPreferences.getInstance()).setInt('pushLastId', maxId);
      }
    } catch (_) {}
  }

  Future<void> show({required int id, required String title, required String body}) async {
    if (!_shown.add(id)) return;
    final android = AndroidNotificationDetails(
      'joelmtrader_alerts',
      'JoelMTrader alerts',
      channelDescription: 'Entries, bot status, and risk alerts',
      importance: Importance.max,
      priority: Priority.max,
      icon: '@drawable/ic_stat_notify',
      largeIcon: const DrawableResourceAndroidBitmap('@mipmap/ic_launcher'),
      color: const Color(0xFF0000FF),
      playSound: true,
      enableVibration: true,
      visibility: NotificationVisibility.public,
      category: AndroidNotificationCategory.status,
      ticker: title,
      styleInformation: BigTextStyleInformation(body),
    );
    const darwin = DarwinNotificationDetails(presentAlert: true, presentBadge: true, presentSound: true, interruptionLevel: InterruptionLevel.timeSensitive);
    const windows = WindowsNotificationDetails(duration: WindowsNotificationDuration.long, scenario: WindowsNotificationScenario.urgent);
    final linux = LinuxNotificationDetails(
      urgency: LinuxNotificationUrgency.critical,
      icon: AssetsLinuxIcon('assets/images/icon.svg'),
    );
    final details = NotificationDetails(android: android, iOS: darwin, macOS: darwin, windows: windows, linux: linux);
    try {
      await _local.show(id: id & 0x7fffffff, title: title, body: body, notificationDetails: details);
    } catch (e) {
      debugPrint('Local notification failed: $e');
    }
  }
}
