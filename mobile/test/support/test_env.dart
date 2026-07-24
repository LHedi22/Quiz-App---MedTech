import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'package:exam_scanner_mobile/config.dart';
import 'package:exam_scanner_mobile/main.dart';
import 'package:exam_scanner_mobile/providers/queue_providers.dart';
import 'package:exam_scanner_mobile/services/api_client.dart';
import 'package:exam_scanner_mobile/services/queue_repository.dart';
import 'package:exam_scanner_mobile/services/sync_service.dart';

/// Test-only helpers for hitting the real local Supabase + FastAPI stack -
/// same rationale and same three flutter_test workarounds as
/// web/test/support/test_env.dart (see [[flutter_test_real_network]] in
/// project memory): fake HttpOverrides, FakeAsync-trapped real awaits, and
/// no platform channel behind shared_preferences under `flutter test`.
bool _initialized = false;

Future<void> initTestSupabase() async {
  if (_initialized) return;
  SharedPreferences.setMockInitialValues({});
  await Supabase.initialize(
    url: AppConfig.supabaseUrl,
    publishableKey: AppConfig.supabasePublishableKey,
    authOptions: const FlutterAuthClientOptions(detectSessionInUri: false),
  );
  _initialized = true;
}

Future<T> withRealNetwork<T>(Future<T> Function() body) async {
  final previous = HttpOverrides.current;
  HttpOverrides.global = null;
  try {
    return await body();
  } finally {
    HttpOverrides.global = previous;
  }
}

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

Future<void> tearDownSignOutIfNeeded() async {
  await withRealNetwork(() async {
    await TestWidgetsFlutterBinding.instance.runAsync(() async {
      if (Supabase.instance.client.auth.currentSession != null) {
        await signOutCurrentUser();
      }
    });
  });
}

/// Mirrors backend/tests' `run_sql` / web/test/support/test_env.dart's
/// `runSql` - needed to seed submissions with known statuses directly,
/// since no API endpoint creates a submission except the real OMR `/scan`
/// pipeline (which needs an actual scannable page image).
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

Future<void> pumpBounded(WidgetTester tester) async {
  for (var i = 0; i < 30; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

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

/// [queueRepositoryProvider]/[syncServiceProvider]/[apiClientProvider] throw
/// unless overridden (see providers/queue_providers.dart) - production
/// `main()` provides them via async setup before `runApp`; widget tests that
/// pump [ExamScannerApp] and navigate anywhere past login (which lands on
/// `/scan`, a queue-dependent screen) need the same real instances.
Future<Widget> buildTestApp() async {
  final repository = QueueRepository(await SharedPreferences.getInstance());
  final apiClient = ApiClient();
  final syncService = SyncService(repository: repository, api: apiClient);
  return ProviderScope(
    overrides: [
      apiClientProvider.overrideWithValue(apiClient),
      queueRepositoryProvider.overrideWithValue(repository),
      syncServiceProvider.overrideWithValue(syncService),
    ],
    child: const ExamScannerApp(),
  );
}
