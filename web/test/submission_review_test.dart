import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:exam_scanner_web/screens/results/submission_review_screen.dart';

import 'support/test_env.dart';

/// Subtask 7.5: for a needs_review submission with multiple flagged
/// answers, resolving them one at a time updates the UI reactively (no
/// manual refresh) and the submission only leaves needs_review once every
/// flagged answer is resolved - tested as an explicit boundary, not assumed.
void main() {
  setUpAll(() async {
    await initTestSupabase();
  });

  tearDown(() async {
    await tearDownSignOutIfNeeded();
  });

  testWidgets(
      'resolving flagged answers one at a time updates reactively; '
      'submission only leaves needs_review once all are resolved',
      (tester) async {
    await withRealNetwork(() async {
      final quizId = newTestUuid();
      final q1Id = newTestUuid();
      final q2Id = newTestUuid();
      final versionId = newTestUuid();
      final subId = newTestUuid();
      // qr_id is globally unique-constrained and the email is unique too -
      // both must be per-run, not fixed strings, or a repeat run collides
      // with the previous run's leftover rows (this bit us: the very first
      // run left rows behind since this test had no teardown for its seed
      // data, only for the auth session).
      final uniqueSuffix = newTestUuid();
      late String userId;

      // Setup (real sign-up, DB seed via docker exec, and the screen's own
      // provider-driven fetch on pumpWidget) is all real I/O, kept in one
      // real zone (see tapAndAwaitRealNetwork's docs for why).
      await tester.runAsync(() async {
        userId = await signUpFreshProfessor('review');

        await runSql('''
          insert into users (id, email) values ('$userId', 'review-$uniqueSuffix@example.com')
            on conflict (id) do nothing;
          insert into quizzes (id, owner_id, title) values ('$quizId', '$userId', 'Review test quiz');
          insert into questions (id, quiz_id, text, options, correct_option, order_index) values
            ('$q1Id', '$quizId', 'Q1?', '["A","B","C","D"]', 'B', 1),
            ('$q2Id', '$quizId', 'Q2?', '["A","B","C","D"]', 'C', 2);
          insert into versions (id, quiz_id, version_number, qr_id, question_order, option_order) values
            ('$versionId', '$quizId', 1, 'review-test-qr-$uniqueSuffix',
             '["$q1Id","$q2Id"]',
             '{"$q1Id": [0,1,2,3], "$q2Id": [0,1,2,3]}');
          insert into submissions (id, version_id, status) values ('$subId', '$versionId', 'needs_review');
          insert into answers (submission_id, question_no, detected_option, confidence, flagged) values
            ('$subId', 1, null, 0.3, true),
            ('$subId', 2, null, 0.3, true);
        ''');

        await tester.pumpWidget(ProviderScope(
          child: MaterialApp(
            home: SubmissionReviewScreen(submissionId: subId, quizId: quizId),
          ),
        ));
        // A duration passed to pump() advances the *fake* frame clock, which
        // is paused while inside runAsync - a real delay is needed first.
        // Two rounds: one for the real fetch, one more because the screen
        // copies the future's data into local state via a post-frame
        // callback (not synchronously in the same frame the future resolves).
        await Future<void>.delayed(const Duration(seconds: 1));
        await tester.pump();
        await Future<void>.delayed(const Duration(milliseconds: 500));
        await tester.pump();
      });
      await pumpBounded(tester);

      expect(find.text('2 flagged question(s) remaining:'), findsOneWidget);
      expect(find.text('Status: needs_review'), findsOneWidget);

      // Resolve question 1 (correct answer is 'B'). Row keys are per-answer-id
      // (unknown here), so find the row by its "Question 1" text instead.
      final q1RowFinder = find.ancestor(
        of: find.textContaining('Question 1'),
        matching: find.byWidgetPredicate((w) => w.key.toString().contains('flagged_answer_')),
      );
      expect(q1RowFinder, findsOneWidget);

      final q1Dropdown = find.descendant(
        of: q1RowFinder,
        matching: find.byWidgetPredicate((w) => w is DropdownButton<String>),
      );
      await tester.tap(q1Dropdown);
      await pumpBounded(tester);
      await tester.tap(find.text('B').last);
      await pumpBounded(tester);

      final q1SaveButton = find.descendant(
        of: q1RowFinder,
        matching: find.byWidgetPredicate((w) => w is ElevatedButton),
      );
      await tapAndAwaitRealNetwork(tester, q1SaveButton);

      // Boundary: only 1 of 2 flagged answers resolved -> must still be
      // needs_review, reactively reflecting the new remaining-count, not a
      // stale pre-correction view.
      expect(find.text('Status: needs_review'), findsOneWidget);
      expect(find.text('1 flagged question(s) remaining:'), findsOneWidget);
      expect(find.textContaining('Question 1'), findsNothing);
      expect(find.textContaining('Question 2'), findsOneWidget);

      // Resolve question 2 (correct answer is 'C') - the last flagged one.
      final q2RowFinder = find.ancestor(
        of: find.textContaining('Question 2'),
        matching: find.byWidgetPredicate((w) => w.key.toString().contains('flagged_answer_')),
      );
      final q2Dropdown = find.descendant(
        of: q2RowFinder,
        matching: find.byWidgetPredicate((w) => w is DropdownButton<String>),
      );
      await tester.tap(q2Dropdown);
      await pumpBounded(tester);
      await tester.tap(find.text('C').last);
      await pumpBounded(tester);

      final q2SaveButton = find.descendant(
        of: q2RowFinder,
        matching: find.byWidgetPredicate((w) => w is ElevatedButton),
      );
      await tapAndAwaitRealNetwork(tester, q2SaveButton);

      // Reactive update with no manual refresh: the same pumped widget tree
      // now shows finalized, purely from local state updated by the PATCH
      // response.
      expect(find.text('Status: needs_review'), findsNothing);
      expect(
        find.text('All flagged answers resolved — this submission is no longer needs_review.'),
        findsOneWidget,
      );
      expect(find.textContaining('Total score:'), findsOneWidget);

      await tester.runAsync(() async {
        await runSql('''
          delete from answers where submission_id = '$subId';
          delete from submissions where id = '$subId';
          delete from versions where id = '$versionId';
          delete from questions where quiz_id = '$quizId';
          delete from quizzes where id = '$quizId';
        ''');
      });
    });
  });
}
