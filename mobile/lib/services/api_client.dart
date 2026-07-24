import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

import '../config.dart';
import '../models/scan_result.dart';

class ApiException implements Exception {
  final int statusCode;
  final String message;
  ApiException(this.statusCode, this.message);

  @override
  String toString() => 'ApiException($statusCode): $message';
}

/// Abstraction over the backend calls the mobile app needs. [SyncService]
/// depends on this interface, not the concrete [ApiClient], so retry/backoff
/// logic can be unit-tested against a fake implementation while [ApiClient]
/// itself is exercised directly in real-network integration tests (mirrors
/// web/lib/services/api_client.dart's Bearer-token pattern).
abstract class ScanApi {
  Future<ScanResult> scanSubmission(Uint8List imageBytes, {String? studentId});
  Future<SubmissionStatus> getSubmissionStatus(String submissionId);
}

class ApiClient implements ScanApi {
  final http.Client _client;
  final String baseUrl;

  ApiClient({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        baseUrl = baseUrl ?? AppConfig.backendUrl;

  /// See web/lib/services/api_client.dart's identical method for why tests
  /// that construct a fresh ApiClient must call this in teardown.
  void close() => _client.close();

  Map<String, String> get _authHeaders {
    final token = Supabase.instance.client.auth.currentSession?.accessToken;
    return token == null ? {} : {'Authorization': 'Bearer $token'};
  }

  Never _throwForStatus(http.Response response) {
    dynamic body;
    try {
      body = jsonDecode(response.body);
    } catch (_) {
      body = response.body;
    }
    final message = body is Map && body['detail'] != null ? body['detail'].toString() : body.toString();
    throw ApiException(response.statusCode, message);
  }

  @override
  Future<ScanResult> scanSubmission(Uint8List imageBytes, {String? studentId}) async {
    final uri = Uri.parse('$baseUrl/scan').replace(
      queryParameters: studentId == null ? null : {'student_id': studentId},
    );
    final request = http.MultipartRequest('POST', uri)
      ..headers.addAll(_authHeaders)
      ..files.add(http.MultipartFile.fromBytes('file', imageBytes, filename: 'scan.jpg'));
    final streamed = await _client.send(request);
    final response = await http.Response.fromStream(streamed);
    if (response.statusCode != 201) _throwForStatus(response);
    return ScanResult.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  @override
  Future<SubmissionStatus> getSubmissionStatus(String submissionId) async {
    final response = await _client.get(
      Uri.parse('$baseUrl/submissions/$submissionId'),
      headers: _authHeaders,
    );
    if (response.statusCode != 200) _throwForStatus(response);
    return SubmissionStatus.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }
}
