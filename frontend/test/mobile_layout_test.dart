import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:waya_fx_bot/core/api.dart';
import 'package:waya_fx_bot/core/app_state.dart';
import 'package:waya_fx_bot/core/theme.dart';
import 'package:waya_fx_bot/pages/news_page.dart';
import 'package:waya_fx_bot/pages/reports_page.dart';
import 'package:waya_fx_bot/pages/shell.dart';

class _Adapter implements HttpClientAdapter {
  @override
  void close({bool force = false}) {}

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? requestStream, Future<void>? cancelFuture) async {
    final path = options.uri.path;
    final Object body;
    if (path.endsWith('/api/auth/me')) {
      body = {'username': 'joel@wayaspot.com', 'role': 'SUPER_ADMIN'};
    } else if (path.endsWith('/api/bot/status')) {
      body = {'engineOnline': true, 'running': false, 'engine': {'status': 'STOPPED'}};
    } else if (path.endsWith('/api/reports/sessions')) {
      body = [
        {
          'id': 12,
          'status': 'STOPPED',
          'startedAt': 1760900000,
          'stoppedAt': 1760910000,
          'openingBalance': 12,
          'closingBalance': 18.4,
          'emailSent': true,
          'note': null,
          'stats': {'netProfit': 6.4, 'trades': 3, 'winRate': 0.66, 'profitFactor': 2.1},
        }
      ];
    } else if (path.endsWith('/api/market/news')) {
      body = {
        'blocked': {
          'XAUUSD': {'blocked': false},
          'EURUSD': {'blocked': true, 'reason': 'High-impact USD news in 20 minutes'},
        },
        'events': [
          {'time': 1761000000, 'currency': 'USD', 'impact': 'High', 'forecast': '0.3%', 'title': 'Consumer price index year over year'},
        ],
        'headlines': [
          {'title': 'Gold holds near the session high as the dollar softens', 'source': 'Reuters', 'time': 1760990000, 'symbols': ['XAUUSD']},
        ],
      };
    } else if (path.endsWith('/api/dashboard')) {
      body = {
        'bot': {'engineOnline': true, 'running': false, 'needsMt5': false},
        'engine': {'status': 'STOPPED', 'mode': 'mt5', 'broker': {'demo': true}, 'stats': {}},
        'account': {'balance': 12, 'equity': 12, 'profit': 0, 'login': 81882316},
        'today': {'netProfit': 0, 'trades': 0},
        'all': {'wins': 1, 'losses': 0, 'winRate': 1, 'profitFactor': 1, 'netProfit': 1},
        'openCount': 0,
        'closedTrades': 1,
        'scan': {'why': 'Press Trade Now to start. The bot will analyse and only trade when conditions are right.'},
      };
    } else if (path.endsWith('/api/trades/closed')) {
      body = {'content': [], 'totalPages': 1};
    } else if (path.endsWith('/api/market/quotes')) {
      body = [
        {'symbol': 'XAUUSD', 'bid': 2650.12, 'spread': 0.2, 'digits': 2, 'changePct': 0.12, 'spark': [1, 2, 3, 2.5, 4]},
      ];
    } else {
      body = {};
    }
    return ResponseBody.fromString(jsonEncode(body), 200, headers: {Headers.contentTypeHeader: [Headers.jsonContentType]});
  }
}

Future<AppState> _state() async {
  SharedPreferences.setMockInitialValues({'apiUrl': 'http://example.test', 'theme': 'light'});
  final state = AppState();
  await state.init();
  state.api = Api('http://example.test', token: 'test', dio: Dio()..httpClientAdapter = _Adapter());
  state.user = {'username': 'joel@wayaspot.com', 'role': 'SUPER_ADMIN'};
  return state;
}

Widget _app(AppState state, Widget home) {
  return ChangeNotifierProvider.value(
    value: state,
    child: MaterialApp(theme: buildTheme(Brightness.light), home: home),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<void> phone(WidgetTester tester) async {
    tester.view.physicalSize = const Size(390, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  testWidgets('reports page stays horizontal on a phone', (tester) async {
    await phone(tester);
    final state = await _state();
    await tester.pumpWidget(_app(state, const Scaffold(body: ReportsPage())));
    await tester.pumpAndSettle();
    expect(find.text('A push notification is sent whenever you press Stop trade'), findsOneWidget);
    expect(find.text('Send daily digest'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('market headlines stay horizontal on a phone', (tester) async {
    await phone(tester);
    final state = await _state();
    await tester.pumpWidget(_app(state, const Scaffold(body: NewsPage())));
    await tester.pumpAndSettle();
    expect(find.text('Market headlines'), findsOneWidget);
    expect(find.text('Filter by the pair you want to read'), findsOneWidget);
    expect(find.text('ALL'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('shell status sits under the title on a phone', (tester) async {
    await phone(tester);
    final state = await _state();
    await tester.pumpWidget(_app(state, const Shell()));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('STOPPED'), findsWidgets);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 1));
  });
}
