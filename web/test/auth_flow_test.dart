import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'package:exam_scanner_web/main.dart';

import 'support/test_env.dart';

/// Subtask 7.1: auth (sign up/in/out) works against a real Supabase project,
/// and unauthenticated users are redirected away from protected routes -
/// both verified explicitly against the real local Supabase Auth instance
/// (not a mock), by pumping the actual app and tapping its real screens.
void main() {
  setUpAll(() async {
    await initTestSupabase();
  });

  tearDown(() async {
    // Not just `withRealNetwork` - a *direct* (non-tap) real network call
    // like this one also needs `runAsync`, or it never resolves; see
    // tapAndAwaitRealNetwork's docs for the full explanation. tearDown has
    // no WidgetTester, so this goes through the binding singleton instead.
    await withRealNetwork(() async {
      await TestWidgetsFlutterBinding.instance.runAsync(() async {
        if (Supabase.instance.client.auth.currentSession != null) {
          await signOutCurrentUser();
        }
      });
    });
  });

  testWidgets(
      'unauthenticated user landing on a protected route is redirected to /login',
      (tester) async {
    await withRealNetwork(() async {
      await tester.pumpWidget(const ProviderScope(child: ExamScannerApp()));
      await pumpBounded(tester);

      // initialLocation is '/quizzes' (protected); with no session, the
      // redirect guard must land us on /login instead.
      expect(find.byKey(const Key('login_email_field')), findsOneWidget);
      expect(find.text('Quizzes'), findsNothing);
    });
  });

  testWidgets('sign up grants access to protected routes against the real Supabase project',
      (tester) async {
    await withRealNetwork(() async {
      await tester.pumpWidget(const ProviderScope(child: ExamScannerApp()));
      await pumpBounded(tester);

      await tester.tap(find.text("Don't have an account? Sign up"));
      await pumpBounded(tester);
      expect(find.byKey(const Key('signup_email_field')), findsOneWidget);

      final email = 'authtest-${DateTime.now().microsecondsSinceEpoch}@example.com';
      await tester.enterText(find.byKey(const Key('signup_email_field')), email);
      await tester.enterText(find.byKey(const Key('signup_password_field')), 'test-password-123!');
      await tapAndAwaitRealNetwork(tester, find.byKey(const Key('signup_submit_button')));

      // Real signUp succeeded and the redirect guard reacted to the real
      // session: we should now be on the (protected) quizzes list, inside
      // the app shell.
      expect(Supabase.instance.client.auth.currentSession, isNotNull);
      expect(find.text('Quizzes'), findsWidgets);
      expect(find.byKey(const Key('signup_email_field')), findsNothing);

      // Landing on /quizzes triggers QuizzesListScreen's own real fetch
      // (quizzesProvider); it must be given real time to finish inside this
      // same runAsync-covered window, or it's still in flight when the
      // ProviderScope is torn down at test end and throws asynchronously
      // later ("used QuizzesNotifier after dispose") - which flutter_test
      // then attributes to whatever unrelated test happens to be running
      // when that dangling future finally resolves.
      await tester.runAsync(() => Future<void>.delayed(const Duration(seconds: 1)));
      await pumpBounded(tester);
    });
  });

  testWidgets('log out redirects back to /login', (tester) async {
    await withRealNetwork(() async {
      await tester.runAsync(() => signUpFreshProfessor('logouttest'));

      await tester.pumpWidget(const ProviderScope(child: ExamScannerApp()));
      // Lands directly on /quizzes (session already exists before the first
      // pump), so its real fetch needs the same real-wait treatment here.
      await tester.runAsync(() => Future<void>.delayed(const Duration(seconds: 1)));
      await pumpBounded(tester);
      expect(find.text('Quizzes'), findsWidgets);

      await tester.tap(find.text('Account'));
      await pumpBounded(tester);

      await tapAndAwaitRealNetwork(tester, find.byKey(const Key('sign_out_button')));

      expect(Supabase.instance.client.auth.currentSession, isNull);
      expect(find.byKey(const Key('login_email_field')), findsOneWidget);
    });
  });

  testWidgets('log in with an existing account grants access against the real project',
      (tester) async {
    await withRealNetwork(() async {
      final email = 'logintest-${DateTime.now().microsecondsSinceEpoch}@example.com';
      const password = 'test-password-123!';
      await tester.runAsync(() async {
        await Supabase.instance.client.auth.signUp(email: email, password: password);
        await signOutCurrentUser();
      });

      await tester.pumpWidget(const ProviderScope(child: ExamScannerApp()));
      await pumpBounded(tester);
      expect(find.byKey(const Key('login_email_field')), findsOneWidget);

      await tester.enterText(find.byKey(const Key('login_email_field')), email);
      await tester.enterText(find.byKey(const Key('login_password_field')), password);
      await tapAndAwaitRealNetwork(tester, find.byKey(const Key('login_submit_button')));

      expect(Supabase.instance.client.auth.currentSession, isNotNull);
      expect(find.text('Quizzes'), findsWidgets);

      // See the "sign up" test's comment: give QuizzesListScreen's own
      // fetch real time to finish before this test (and its ProviderScope)
      // ends.
      await tester.runAsync(() => Future<void>.delayed(const Duration(seconds: 1)));
      await pumpBounded(tester);
    });
  });
}
