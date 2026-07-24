import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

import '../config.dart';
import '../models/quiz.dart';
import '../models/submission.dart';

class ApiException implements Exception {
  final int statusCode;
  final String message;
  ApiException(this.statusCode, this.message);

  @override
  String toString() => 'ApiException($statusCode): $message';
}

/// Thrown by [ApiClient.uploadExcel] on a 422 from Phase 2's parser, carrying
/// every bad row's number + reasons (never just the first) so the UI can
/// surface all of them at once.
class ExcelValidationException implements Exception {
  final List<RowError> errors;
  ExcelValidationException(this.errors);
}

/// Thin wrapper around the FastAPI backend. Every call attaches the current
/// Supabase session's access token as a Bearer header - the backend verifies
/// it via JWKS (see backend/app/services/auth.py) and scopes quiz ownership
/// to the resulting user id.
class ApiClient {
  final http.Client _client;
  final String baseUrl;

  ApiClient({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        baseUrl = baseUrl ?? AppConfig.backendUrl;

  /// Closes the underlying HTTP client, releasing any pooled keep-alive
  /// connections. The app itself never needs this (it lives for the app's
  /// whole lifetime), but tests that construct a fresh `ApiClient` should
  /// call it at the end, or a dangling keep-alive timer trips
  /// flutter_test's "no pending timers" teardown check.
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

  Future<Quiz> createQuiz(String title) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/quizzes'),
      headers: {'Content-Type': 'application/json', ..._authHeaders},
      body: jsonEncode({'title': title}),
    );
    if (response.statusCode != 201) _throwForStatus(response);
    return Quiz.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<List<Quiz>> listQuizzes() async {
    final response = await _client.get(Uri.parse('$baseUrl/quizzes'), headers: _authHeaders);
    if (response.statusCode != 200) _throwForStatus(response);
    return (jsonDecode(response.body) as List)
        .map((q) => Quiz.fromJson(q as Map<String, dynamic>))
        .toList();
  }

  /// Uploads an Excel file's bytes for [quizId]. Returns the number of
  /// questions inserted on success; throws [ExcelValidationException] with
  /// every bad row on a 422.
  Future<int> uploadExcel(String quizId, Uint8List bytes, String filename) async {
    final request = http.MultipartRequest('POST', Uri.parse('$baseUrl/quizzes/$quizId/upload'))
      ..headers.addAll(_authHeaders)
      ..files.add(http.MultipartFile.fromBytes('file', bytes, filename: filename));
    final streamed = await _client.send(request);
    final response = await http.Response.fromStream(streamed);

    if (response.statusCode == 422) {
      final detail = (jsonDecode(response.body) as Map<String, dynamic>)['detail'] as Map<String, dynamic>;
      final errors =
          (detail['errors'] as List).map((e) => RowError.fromJson(e as Map<String, dynamic>)).toList();
      throw ExcelValidationException(errors);
    }
    if (response.statusCode != 201) _throwForStatus(response);
    return (jsonDecode(response.body) as Map<String, dynamic>)['questions_inserted'] as int;
  }

  Future<int> generateVersions(String quizId, int count) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/quizzes/$quizId/versions'),
      headers: {'Content-Type': 'application/json', ..._authHeaders},
      body: jsonEncode({'count': count}),
    );
    if (response.statusCode != 201) _throwForStatus(response);
    return (jsonDecode(response.body) as Map<String, dynamic>)['versions_created'] as int;
  }

  Future<List<QuizVersion>> listVersions(String quizId) async {
    final response =
        await _client.get(Uri.parse('$baseUrl/quizzes/$quizId/versions'), headers: _authHeaders);
    if (response.statusCode != 200) _throwForStatus(response);
    return (jsonDecode(response.body) as List)
        .map((v) => QuizVersion.fromJson(v as Map<String, dynamic>))
        .toList();
  }

  /// Fetches the signed download URL for a version's PDF, then downloads the
  /// actual bytes from that URL (Supabase Storage, a different origin).
  Future<Uint8List> downloadVersionPdf(String versionId) async {
    final response =
        await _client.get(Uri.parse('$baseUrl/versions/$versionId/pdf'), headers: _authHeaders);
    if (response.statusCode != 200) _throwForStatus(response);
    final url = (jsonDecode(response.body) as Map<String, dynamic>)['url'] as String;
    final pdfResponse = await _client.get(Uri.parse(url));
    if (pdfResponse.statusCode != 200) {
      throw ApiException(pdfResponse.statusCode, 'failed to download PDF from storage');
    }
    return pdfResponse.bodyBytes;
  }

  /// Lists submissions for one quiz (mixed statuses by default), backing
  /// the results dashboard.
  Future<List<Submission>> listQuizSubmissions(String quizId, {String? status}) async {
    final uri = Uri.parse('$baseUrl/quizzes/$quizId/submissions').replace(
      queryParameters: status == null ? null : {'status': status},
    );
    final response = await _client.get(uri, headers: _authHeaders);
    if (response.statusCode != 200) _throwForStatus(response);
    return (jsonDecode(response.body) as List)
        .map((s) => Submission.fromJson(s as Map<String, dynamic>))
        .toList();
  }

  /// Fetches one submission with its full answer detail - needed by the
  /// review screen before a professor has anything to correct.
  Future<Submission> getSubmission(String submissionId) async {
    final response = await _client.get(
      Uri.parse('$baseUrl/submissions/$submissionId'),
      headers: _authHeaders,
    );
    if (response.statusCode != 200) _throwForStatus(response);
    return Submission.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<Submission> correctAnswer(String submissionId, String answerId, String correctOption) async {
    final response = await _client.patch(
      Uri.parse('$baseUrl/submissions/$submissionId/answers/$answerId'),
      headers: {'Content-Type': 'application/json', ..._authHeaders},
      body: jsonEncode({'correct_option': correctOption}),
    );
    if (response.statusCode != 200) _throwForStatus(response);
    return Submission.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }
}
