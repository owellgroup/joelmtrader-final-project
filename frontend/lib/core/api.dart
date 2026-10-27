import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

class ApiException implements Exception {
  final String message;
  final int? status;
  ApiException(this.message, [this.status]);
  @override
  String toString() => message;
}

class Api {
  String baseUrl;
  String? token;
  void Function()? onUnauthorized;
  late Dio _dio;

  Api(this.baseUrl, {this.token, Dio? dio}) {
    _dio = dio ??
        Dio(BaseOptions(
          connectTimeout: const Duration(seconds: 12),
          receiveTimeout: const Duration(seconds: 90),
          // sendTimeout on Web GETs spam the console and is ignored without a body.
          sendTimeout: kIsWeb ? null : const Duration(seconds: 45),
          responseType: ResponseType.json,
          // Never force application/json on every request — that triggers useless CORS preflights on GET.
          contentType: null,
          headers: const {
            'Accept': 'application/json',
          },
        ));
  }

  String get _base => baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;

  Future<dynamic> _call(String method, String path, {Map<String, dynamic>? query, dynamic body, bool hasBody = false}) async {
    try {
      final headers = <String, dynamic>{
        if (token != null) 'Authorization': 'Bearer $token',
        if (hasBody) Headers.contentTypeHeader: Headers.jsonContentType,
      };
      final res = await _dio.request(
        '$_base$path',
        data: hasBody ? body : null,
        queryParameters: query,
        options: Options(method: method, headers: headers),
      );
      return res.data;
    } on DioException catch (e) {
      final status = e.response?.statusCode;
      if (status == 401 && !path.contains('/auth/login')) {
        onUnauthorized?.call();
      }
      String msg;
      final data = e.response?.data;
      if (data is Map && data['error'] != null) {
        msg = data['error'].toString();
      } else if (data is Map && data['detail'] != null) {
        msg = data['detail'].toString();
      } else if (status == null) {
        msg = 'Cannot reach the server at $_base. Check the URL and that the backend is running.';
      } else {
        msg = 'Request failed ($status)';
      }
      throw ApiException(msg, status);
    }
  }

  Future<dynamic> get(String path, {Map<String, dynamic>? query}) => _call('GET', path, query: query);
  Future<dynamic> post(String path, {dynamic body}) => _call('POST', path, body: body ?? const {}, hasBody: true);
  Future<dynamic> put(String path, {dynamic body}) => _call('PUT', path, body: body ?? const {}, hasBody: true);
  Future<dynamic> delete(String path) => _call('DELETE', path);
}
