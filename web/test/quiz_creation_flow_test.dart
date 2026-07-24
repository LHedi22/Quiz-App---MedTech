import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:exam_scanner_web/screens/quizzes/quiz_create_screen.dart';

import 'support/test_env.dart';

Future<PickedExcelFile> _fakePickFile(String fixtureName) async {
  final bytes = await fixtureFile(fixtureName).readAsBytes();
  return PickedExcelFile(Uint8List.fromList(bytes), fixtureName);
}

Widget _wrap(Widget child) => ProviderScope(child: MaterialApp(home: Scaffold(body: child)));

/// Subtask 7.2: create quiz -> upload Excel -> show parsed questions/errors
/// -> generate versions, verified end-to-end against the real backend.
void main() {
  setUpAll(() async {
    await initTestSupabase();
  });

  tearDown(() async {
    await tearDownSignOutIfNeeded();
  });

  testWidgets('uploading the invalid fixture surfaces every row error in the UI', (tester) async {
    await withRealNetwork(() async {
      await tester.runAsync(() => signUpFreshProfessor('quizcreate-invalid'));

      await tester.pumpWidget(_wrap(
        QuizCreateScreen(pickFile: () => _fakePickFile('multiple_errors.xlsx')),
      ));
      await pumpBounded(tester);

      await tester.enterText(find.byKey(const Key('quiz_title_field')), 'Invalid upload quiz');
      await tapAndAwaitRealNetwork(tester, find.byKey(const Key('create_quiz_button')));

      await tapAndAwaitRealNetwork(tester, find.byKey(const Key('upload_excel_button')));

      // Per backend/tests/test_parsing.py's multiple_errors.xlsx fixture:
      // row 2 has one bad-row reason, row 3 has two - both rows, and every
      // one of their reasons, must appear (not just the first bad row).
      expect(find.textContaining('question_text is empty'), findsOneWidget);
      expect(find.textContaining('option_b is empty'), findsOneWidget);
      expect(
        find.textContaining("correct_option must be exactly one of A/B/C/D, got 'E'"),
        findsOneWidget,
      );
      expect(find.byKey(const Key('row_error_2')), findsOneWidget);
      expect(find.byKey(const Key('row_error_3')), findsOneWidget);
    });
  });

  testWidgets(
      'successful flow ends with N versions visible and downloadable against the real backend',
      (tester) async {
    await withRealNetwork(() async {
      await tester.runAsync(() => signUpFreshProfessor('quizcreate-valid'));

      await tester.pumpWidget(_wrap(
        QuizCreateScreen(pickFile: () => _fakePickFile('valid.xlsx')),
      ));
      await pumpBounded(tester);

      await tester.enterText(find.byKey(const Key('quiz_title_field')), 'Valid upload quiz');
      await tapAndAwaitRealNetwork(tester, find.byKey(const Key('create_quiz_button')));

      await tapAndAwaitRealNetwork(tester, find.byKey(const Key('upload_excel_button')));
      expect(find.textContaining('question(s) uploaded'), findsOneWidget);

      await tester.enterText(find.byKey(const Key('version_count_field')), '3');
      await tapAndAwaitRealNetwork(tester, find.byKey(const Key('generate_versions_button')));

      expect(find.text('3 version(s) generated.'), findsOneWidget);
      expect(find.byKey(const Key('view_versions_button')), findsOneWidget);
    });
  });
}
