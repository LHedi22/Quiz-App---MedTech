import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:exam_scanner_web/screens/results/results_screen.dart';
import 'package:exam_scanner_web/services/api_client.dart';

import 'support/test_env.dart';

/// Subtask 7.4: dashboard correctly reflects backend state for a seeded set
/// of submissions with mixed statuses - exact counts and data, not just
/// "list renders" - against the real backend + a directly-seeded DB.
void main() {
  setUpAll(() async {
    await initTestSupabase();
  });

  tearDown(() async {
    await tearDownSignOutIfNeeded();
  });

  testWidgets('dashboard shows exact counts/data for mixed-status submissions and filters by status',
      (tester) async {
    await withRealNetwork(() async {
      final api = ApiClient();

      // Setup, the screen's own provider-driven fetch on pumpWidget, and
      // the status-filter tap are all real network/process I/O - kept in
      // one real zone throughout (see tapAndAwaitRealNetwork's docs).
      await tester.runAsync(() async {
        await signUpFreshProfessor('dashboard');

        final quiz = await api.createQuiz('Dashboard widget test quiz');
        final bytes = await fixtureFile('valid.xlsx').readAsBytes();
        await api.uploadExcel(quiz.id, Uint8List.fromList(bytes), 'valid.xlsx');
        await api.generateVersions(quiz.id, 1);
        final versions = await api.listVersions(quiz.id);
        final versionId = versions.single.id;

        // Seed three submissions with distinct statuses directly (no API
        // endpoint creates submissions except the real OMR /scan pipeline,
        // which needs an actual scanned image - not this test's concern).
        await runSql('''
          insert into submissions (version_id, status, total_score)
            values ('$versionId', 'finalized', 4.0);
          insert into submissions (version_id, status)
            values ('$versionId', 'needs_review');
          insert into submissions (version_id, status)
            values ('$versionId', 'pending');
        ''');

        await tester.pumpWidget(ProviderScope(
          child: MaterialApp(home: ResultsScreen()),
        ));
        // Two sequential real fetches happen here, not one: quizzesProvider
        // loads first, then - once build() picks a default quiz - a second,
        // separate fetch for quizSubmissionsProvider starts. Each needs its
        // own real-delay-then-rebuild round, not a single wait.
        await Future<void>.delayed(const Duration(seconds: 1));
        await tester.pump();
        await Future<void>.delayed(const Duration(seconds: 1));
        await tester.pump();
      });
      await pumpBounded(tester);

      expect(find.text('Status: finalized'), findsOneWidget);
      expect(find.text('Status: needs_review'), findsOneWidget);
      expect(find.text('Status: pending'), findsOneWidget);
      expect(find.textContaining('Score: 4.0'), findsOneWidget);
      // Only the needs_review submission should show a Review action.
      expect(find.text('Review'), findsOneWidget);

      // Filter to needs_review only: exactly one row should remain.
      await tester.tap(find.byKey(const Key('status_filter')));
      await pumpBounded(tester);
      // The dropdown item's own selection callback only fires once its
      // popup route finishes closing (a microtask-driven `.then()`, not
      // necessarily settled by the time a single post-tap delay elapses) -
      // several delay+pump rounds in the *same* runAsync call avoid
      // orphaning that continuation outside the real zone by exiting too
      // early, unlike one long delay racing against an unknown start time.
      await tester.runAsync(() async {
        await tester.tap(find.text('needs_review').last);
        for (var i = 0; i < 5; i++) {
          await Future<void>.delayed(const Duration(milliseconds: 800));
          await tester.pump();
        }
      });
      await pumpBounded(tester);

      expect(find.text('Status: needs_review'), findsOneWidget);
      expect(find.text('Status: finalized'), findsNothing);
      expect(find.text('Status: pending'), findsNothing);
      api.close();
    });
  });
}
