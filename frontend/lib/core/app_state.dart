import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'api.dart';

/// Public backend gateway (nginx → Java API). Also works on :8080 (API direct).
/// Override at build time with --dart-define=API_URL=http://145.241.187.174:8088
const String kDefaultApiUrl = String.fromEnvironment('API_URL', defaultValue: 'http://145.241.187.174:8088');

String _normalizeApiUrl(String? raw) {
  var url = (raw ?? '').trim();
  if (url.endsWith('/')) url = url.substring(0, url.length - 1);
  // Old / broken bookmarks → live gateway
  if (url.isEmpty ||
      url.contains('localhost') ||
      url.contains('127.0.0.1') ||
      url.contains('84.8.131.140') ||
      url.contains('144.241.187.174') ||
      url == 'http://145.241.187.174' ||
      url == 'https://145.241.187.174') {
    return kDefaultApiUrl;
  }
  return url;
}

/// Holds session (JWT persisted on-device -> stays logged in until you log out) and theme.
class AppState extends ChangeNotifier {
  late SharedPreferences _prefs;
  late Api api;
  bool ready = false;
  bool offlineWarning = false;
  int unreadAlerts = 0;
  Map<String, dynamic>? user;
  ThemeMode themeMode = ThemeMode.light; // white by default

  bool get loggedIn => api.token != null && user != null;
  bool get isSuper => user?['role'] == 'SUPER_ADMIN';

  Future<void> init() async {
    _prefs = await SharedPreferences.getInstance();
    final url = _normalizeApiUrl(_prefs.getString('apiUrl'));
    await _prefs.setString('apiUrl', url);
    final token = _prefs.getString('token');
    api = Api(url, token: token);
    api.onUnauthorized = () => logout(silent: false);
    final t = _prefs.getString('theme') ?? 'light';
    themeMode = t == 'dark' ? ThemeMode.dark : (t == 'system' ? ThemeMode.system : ThemeMode.light);
    if (token != null) {
      try {
        user = Map<String, dynamic>.from(await api.get('/api/auth/me'));
      } on ApiException catch (e) {
        if (e.status == 401) {
          await _clearToken();
        } else {
          // Server temporarily unreachable: stay logged in with the cached profile.
          final cached = _prefs.getString('username');
          if (cached != null) {
            user = {'username': cached, 'role': _prefs.getString('role') ?? 'ADMIN'};
            offlineWarning = true;
          }
        }
      }
    }
    ready = true;
    notifyListeners();
  }

  Future<void> login(String url, String username, String password) async {
    api.baseUrl = _normalizeApiUrl(url);
    final res = await api.post('/api/auth/login', body: {'username': username.trim(), 'password': password});
    api.token = res['token'];
    user = Map<String, dynamic>.from(res['user']);
    await _prefs.setString('apiUrl', api.baseUrl);
    await _prefs.setString('token', api.token!);
    await _prefs.setString('username', user!['username']);
    await _prefs.setString('role', user!['role']);
    offlineWarning = false;
    notifyListeners();
  }

  Future<void> setApiUrl(String url) async {
    api.baseUrl = url.trim();
    await _prefs.setString('apiUrl', api.baseUrl);
    notifyListeners();
  }

  String get apiUrl => api.baseUrl;

  Future<void> _clearToken() async {
    api.token = null;
    user = null;
    await _prefs.remove('token');
  }

  Future<void> logout({bool silent = true}) async {
    await _clearToken();
    notifyListeners();
  }

  Future<void> setTheme(ThemeMode m) async {
    themeMode = m;
    await _prefs.setString('theme', m == ThemeMode.dark ? 'dark' : (m == ThemeMode.system ? 'system' : 'light'));
    notifyListeners();
  }

  void toggleTheme() => setTheme(themeMode == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark);

  void setUnreadAlerts(int count) {
    if (unreadAlerts == count) return;
    unreadAlerts = count;
    notifyListeners();
  }
}
