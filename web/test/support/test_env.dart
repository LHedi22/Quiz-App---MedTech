import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:uuid/uuid.dart';

import 'package:exam_scanner_web/config.dart';

/// Test-only helpers for hitting the real local Supabase + FastAPI stack
/// (per CLAUDE.md Section 7's "tests are mandatory" bar and Phase 7's DoD,
/// which explicitly requires a widget/integration test against a real
/// Supabase project - not a mock).
///
/// Discovery: `flutter test`'s widget-test binding (a) has no platform
/// channel behind `shared_preferences` (supabase_flutter's session storage)
/// and (b) installs a fake `HttpOverrides` that fails every real request
/// with a 400 - both needed working around here rather than in every test,
/// since neither is optional for hitting a real backend. (a) is fixed with
/// `SharedPreferences.setMockInitialValues`; (b) is fixed per-call via
/// [withRealNetwork], since the override is zone-scoped, not global.
bool _initialized = false;

Future<void> initTestSupabase() async {
  if (_initialized) return;
  SharedPreferences.setMockInitialValues({});
  await Supabase.initialize(
    url: AppConfig.supabaseUrl,
    publishableKey: AppConfig.supabasePublishableKey,
    // This app only ever does email/password auth (no OAuth/magic-link deep
    // links), and the deep-link listener needs an `app_links` platform
    // channel that doesn't exist in the test environment - disabling it
    // avoids a stray MissingPluginException flutter_test would otherwise
    // count as a test failure regardless of this test's own assertions.
    authOptions: const FlutterAuthClientOptions(detectSessionInUri: false),
  );
  _initialized = true;
}

/// Runs [body] with the fake network-blocking `HttpOverrides` that
/// `flutter_test`'s widget binding installs (globally, via the static
/// `HttpOverrides.global` setter - not zone-scoped) cleared, so every
/// `HttpClient()` constructed during [body] - including the many separate,
/// short-lived ones `package:http`'s `Client()` and gotrue construct per
/// call - is a genuine, independent client.
///
/// Discovery: an earlier version of this helper used `HttpOverrides.runZoned`
/// to hand back one single captured "real" client for every `HttpClient()`
/// call in the zone; that broke on the second network call in a test
/// (`Bad state: Client is closed`), because some request paths call
/// `.close()` on their client when done, and every subsequent call then
/// received that same now-closed instance instead of a fresh one.
Future<T> withRealNetwork<T>(Future<T> Function() body) async {
  final previous = HttpOverrides.current;
  HttpOverrides.global = null;
  try {
    return await body();
  } finally {
    HttpOverrides.global = previous;
  }
}

/// Signs up a brand-new professor against the real local Supabase Auth
/// instance (email confirmations are disabled in supabase/config.toml, so
/// this returns an active session immediately) and returns their user id.
Future<String> signUpFreshProfessor(String emailPrefix) async {
  final email = '$emailPrefix-${DateTime.now().microsecondsSinceEpoch}@example.com';
  final response = await Supabase.instance.client.auth.signUp(
    email: email,
    password: 'test-password-123!',
  );
  return response.user!.id;
}

Future<void> signOutCurrentUser() async {
  await Supabase.instance.client.auth.signOut();
}

/// For `tearDown` blocks, which get no `WidgetTester` - uses the binding
/// singleton's `runAsync` instead, for the same reason any other direct
/// (non-tap) real network call needs it (see [tapAndAwaitRealNetwork]'s
/// docs).
Future<void> tearDownSignOutIfNeeded() async {
  await withRealNetwork(() async {
    await TestWidgetsFlutterBinding.instance.runAsync(() async {
      if (Supabase.instance.client.auth.currentSession != null) {
        await signOutCurrentUser();
      }
    });
  });
}

/// Runs SQL directly against the local Postgres container - mirrors the
/// backend test suite's own `run_sql` helper (see
/// backend/tests/test_rls_cross_user.py), since Dart tests have no
/// psycopg-equivalent and some fixtures (seeding mixed submission statuses)
/// need direct DB writes the API doesn't expose.
Future<void> runSql(String sql) async {
  final process = await Process.start(
    'docker',
    ['exec', '-i', 'supabase_db_exam_scanner', 'psql', '-U', 'postgres', '-d', 'postgres', '-tA'],
  );
  process.stdin.write(sql);
  await process.stdin.close();
  final stderrOutput = await process.stderr.transform(utf8.decoder).join();
  final exitCode = await process.exitCode;
  if (exitCode != 0) {
    throw Exception('runSql failed ($exitCode): $stderrOutput');
  }
}

File fixtureFile(String name) => File('../backend/tests/fixtures/excel/$name');

const _uuid = Uuid();
String newTestUuid() => _uuid.v4();

/// Lets a real network call triggered by an already-dispatched `tester.tap()`
/// actually complete before continuing.
///
/// A tapped button's `onPressed` handler runs in the test's normal FakeAsync
/// zone (not inside any `runAsync` block), so its internal `await`s on real
/// I/O won't resolve on their own - running a short real delay inside
/// `runAsync` gives the real event loop a window to actually deliver that
/// pending I/O's completion (which then resumes the handler's `setState`
/// call, in the zone it started in).
///
/// Taps [finder] and waits for whatever real network call its `onPressed`
/// handler triggers.
///
/// Discovery: a plain `tester.tap()` dispatches its event - and therefore
/// runs the resulting `onPressed` handler and everything it `await`s - in
/// the test's ambient FakeAsync zone, *not* inside any `runAsync` block. A
/// pending real I/O completion's continuation is scheduled via
/// `scheduleMicrotask` in that same zone, and FakeAsync only ever runs
/// microtasks it's told to flush; a later, unrelated `runAsync` call on its
/// own does *not* retroactively drain that stuck queue, no matter how long
/// a real delay it waits on - a signUp
/// button just sat showing its spinner through a full 2-second real wait
/// before this fix. Running the tap itself inside `runAsync` puts the whole
/// handler in the real root zone, where its `await`s resolve normally.
Future<void> tapAndAwaitRealNetwork(
  WidgetTester tester,
  Finder finder, {
  Duration wait = const Duration(seconds: 2),
}) async {
  await tester.runAsync(() async {
    await tester.tap(finder);
    await Future<void>.delayed(wait);
  });
  await pumpBounded(tester);
}

/// Same reasoning as [tapAndAwaitRealNetwork], but for the *initial*
/// `pumpWidget()` call: several screens fetch real data as soon as they're
/// built (a riverpod provider created during `build()`, e.g.
/// `quizzesProvider`/`quizVersionsProvider`), not only in response to a tap -
/// that fetch needs the same real-zone treatment or it never resolves and
/// the screen sits on its loading state forever.
Future<void> pumpWidgetAndAwaitRealNetwork(
  WidgetTester tester,
  Widget widget, {
  Duration wait = const Duration(seconds: 2),
}) async {
  await tester.runAsync(() async {
    await tester.pumpWidget(widget);
    await Future<void>.delayed(wait);
  });
  await pumpBounded(tester);
}

/// A bounded stand-in for `tester.pumpAndSettle()` for pure UI transitions
/// (no real network involved) - same perpetual-animation hang risk applies,
/// so this is used instead everywhere in these tests, not just after real
/// network calls.
Future<void> pumpBounded(WidgetTester tester) async {
  for (var i = 0; i < 30; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}
