import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../support/test_env.dart';

/// Subtask 8.1's DoD: "A professor who signed up on web can log in on
/// mobile with the same credentials, verified against a real (test)
/// Supabase project." Web and mobile both authenticate against the exact
/// same Supabase Auth instance (see lib/config.dart), so signing up here via
/// the SDK directly (rather than driving the actual web app) is a faithful
/// stand-in for "signed up on web" - it exercises the identical backend
/// account creation the web app's signup screen calls.
void main() {
  setUpAll(() async {
    await initTestSupabase();
  });

  tearDown(() async {
    await tearDownSignOutIfNeeded();
  });

  testWidgets('unauthenticated user landing on the app is redirected to /login', (tester) async {
    await withRealNetwork(() async {
      await tester.pumpWidget(await buildTestApp());
      await pumpBounded(tester);

      expect(find.byKey(const Key('login_email_field')), findsOneWidget);
    });
  });

  testWidgets('a professor account created (signed up) on the shared Supabase project logs in on mobile',
      (tester) async {
    await withRealNetwork(() async {
      final email = 'mobile-logintest-${DateTime.now().microsecondsSinceEpoch}@example.com';
      const password = 'test-password-123!';

      // Stands in for "signed up on web" - same Supabase Auth backend both
      // clients point at (lib/config.dart / web/lib/config.dart share the
      // same default local Supabase URL).
      await tester.runAsync(() async {
        await Supabase.instance.client.auth.signUp(email: email, password: password);
        await signOutCurrentUser();
      });

      await tester.pumpWidget(await buildTestApp());
      await pumpBounded(tester);
      expect(find.byKey(const Key('login_email_field')), findsOneWidget);

      await tester.enterText(find.byKey(const Key('login_email_field')), email);
      await tester.enterText(find.byKey(const Key('login_password_field')), password);
      await tapAndAwaitRealNetwork(tester, find.byKey(const Key('login_submit_button')));

      expect(Supabase.instance.client.auth.currentSession, isNotNull);
      expect(find.byKey(const Key('login_email_field')), findsNothing);
      // Redirect guard sends an authenticated session to /scan.
      expect(find.byKey(const Key('capture_button')), findsOneWidget);
    });
  });
}
