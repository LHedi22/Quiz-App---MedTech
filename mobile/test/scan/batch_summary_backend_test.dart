import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

import 'package:exam_scanner_mobile/config.dart';
import 'package:exam_scanner_mobile/models/batch_summary.dart';
import 'package:exam_scanner_mobile/models/scan_queue_item.dart';
import 'package:exam_scanner_mobile/services/api_client.dart';

import '../support/test_env.dart';

/// Subtask 8.4's DoD: "Summary counts exactly match the actual backend
/// submission statuses for that batch, verified against seeded/test data."
///
/// Quiz/version setup here uses raw HTTP directly (not ApiClient) because
/// quiz creation is out of mobile's scope per CLAUDE.md's phase split -
/// mobile only ever calls `/scan` and `GET /submissions/{id}`. Submissions
/// themselves are seeded directly via SQL, same as
/// web/test/results_dashboard_test.dart, since no API endpoint creates one
/// except the real OMR `/scan` pipeline (which needs an actual scannable
/// page image, not this test's concern).
Map<String, String> _authHeaders() {
  final token = Supabase.instance.client.auth.currentSession?.accessToken;
  return token == null ? {} : {'Authorization': 'Bearer $token'};
}

class _QuizAndVersion {
  final String quizId;
  final String versionId;
  _QuizAndVersion(this.quizId, this.versionId);
}

Future<_QuizAndVersion> _createQuizAndVersion(http.Client client) async {
  final createResponse = await client.post(
    Uri.parse('${AppConfig.backendUrl}/quizzes'),
    headers: {'Content-Type': 'application/json', ..._authHeaders()},
    body: jsonEncode({'title': 'Mobile batch summary test quiz'}),
  );
  final quizId = (jsonDecode(createResponse.body) as Map<String, dynamic>)['id'] as String;

  final bytes = await fixtureFile('valid.xlsx').readAsBytes();
  final uploadRequest = http.MultipartRequest(
    'POST',
    Uri.parse('${AppConfig.backendUrl}/quizzes/$quizId/upload'),
  )
    ..headers.addAll(_authHeaders())
    ..files.add(http.MultipartFile.fromBytes('file', Uint8List.fromList(bytes), filename: 'valid.xlsx'));
  final uploadStreamed = await client.send(uploadRequest);
  await http.Response.fromStream(uploadStreamed);

  await client.post(
    Uri.parse('${AppConfig.backendUrl}/quizzes/$quizId/versions'),
    headers: {'Content-Type': 'application/json', ..._authHeaders()},
    body: jsonEncode({'count': 1}),
  );

  final versionsResponse = await client.get(
    Uri.parse('${AppConfig.backendUrl}/quizzes/$quizId/versions'),
    headers: _authHeaders(),
  );
  final versions = jsonDecode(versionsResponse.body) as List;
  return _QuizAndVersion(quizId, versions.single['id'] as String);
}

ScanQueueItem _processedItem(String id, String submissionId, String resultStatus) => ScanQueueItem(
      id: id,
      imageBytes: Uint8List(0),
      createdAt: DateTime.now(),
      state: QueueItemState.processed,
      submissionId: submissionId,
      resultStatus: resultStatus,
    );

void main() {
  setUpAll(() async {
    await initTestSupabase();
  });

  tearDown(() async {
    // Not tearDownSignOutIfNeeded(): this file uses plain test(), not
    // testWidgets(), so no TestWidgetsFlutterBinding/FakeAsync zone exists
    // here and runAsync (which that helper needs) would assert.
    await withRealNetwork(() async {
      if (Supabase.instance.client.auth.currentSession != null) {
        await signOutCurrentUser();
      }
    });
  });

  test('batch summary counts exactly match real backend submission statuses for seeded data', () async {
    await withRealNetwork(() async {
      await signUpFreshProfessor('mobilebatch');
      final httpClient = http.Client();
      final quizAndVersion = await _createQuizAndVersion(httpClient);

      // Seed three submissions with distinct, known statuses directly - the
      // "actual backend submission statuses" this batch's local queue must
      // be reconciled against.
      await runSql('''
        insert into submissions (version_id, status, total_score)
          values ('${quizAndVersion.versionId}', 'finalized', 4.0);
        insert into submissions (version_id, status)
          values ('${quizAndVersion.versionId}', 'needs_review');
        insert into submissions (version_id, status)
          values ('${quizAndVersion.versionId}', 'needs_review');
      ''');

      final listResponse = await httpClient.get(
        Uri.parse('${AppConfig.backendUrl}/quizzes/${quizAndVersion.quizId}/submissions'),
        headers: _authHeaders(),
      );
      final submissionRows = jsonDecode(listResponse.body) as List;
      expect(submissionRows, hasLength(3), reason: 'seed must have inserted exactly 3 rows for this quiz');

      // Build the mobile queue exactly as the sync flow would have left it:
      // one processed item per submission, carrying the status a real
      // `/scan` response would have returned at the time - fetched here via
      // the real `GET /submissions/{id}` endpoint, not copied from the SQL
      // above, so this is checking against the backend's own view.
      final apiClient = ApiClient();
      final queueItems = <ScanQueueItem>[];
      for (final row in submissionRows) {
        final submissionId = row['id'] as String;
        final authoritative = await apiClient.getSubmissionStatus(submissionId);
        queueItems.add(_processedItem('item-$submissionId', submissionId, authoritative.status));
      }
      apiClient.close();
      httpClient.close();

      final summary = BatchSummary.fromItems(queueItems);

      expect(summary.total, 3);
      expect(summary.finalized, 1);
      expect(summary.needsReview, 2);
      expect(summary.pendingSync, 0);
      expect(summary.failed, 0);
    });
  });
}
