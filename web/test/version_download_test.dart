import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:exam_scanner_web/providers/api_providers.dart';
import 'package:exam_scanner_web/screens/quizzes/quiz_versions_screen.dart';
import 'package:exam_scanner_web/services/api_client.dart';

import 'support/test_env.dart';

/// Subtask 7.3: list generated versions with a download button per version;
/// clicking download retrieves the correct, distinct PDF per version.
void main() {
  setUpAll(() async {
    await initTestSupabase();
  });

  tearDown(() async {
    await tearDownSignOutIfNeeded();
  });

  testWidgets('downloading each version retrieves distinct PDFs matching backend storage',
      (tester) async {
    await withRealNetwork(() async {
      final api = ApiClient();
      final downloaded = <String, Uint8List>{};
      late List<dynamic> versions;

      // Everything here is real network (setup calls, the screen's own
      // provider-driven fetch on pumpWidget, and each download tap) - all
      // kept inside one real (non-FakeAsync) zone so every await actually
      // resolves; see pumpWidgetAndAwaitRealNetwork/tapAndAwaitRealNetwork's
      // docs for why a plain pumpWidget/tap here would just hang instead.
      await tester.runAsync(() async {
        await signUpFreshProfessor('versiondownload');

        final quiz = await api.createQuiz('Download test quiz');
        final bytes = await fixtureFile('valid.xlsx').readAsBytes();
        await api.uploadExcel(quiz.id, Uint8List.fromList(bytes), 'valid.xlsx');
        await api.generateVersions(quiz.id, 3);
        versions = await api.listVersions(quiz.id);
        expect(versions.length, 3);

        await tester.pumpWidget(ProviderScope(
          overrides: [apiClientProvider.overrideWithValue(api)],
          child: MaterialApp(
            home: QuizVersionsScreen(
              quizId: quiz.id,
              quizTitle: quiz.title,
              downloadBytes: (bytes, filename) => downloaded[filename] = bytes,
            ),
          ),
        ));
        // `tester.pump(duration)` advances the *fake* frame clock, which is
        // paused for the whole time we're inside `runAsync` - waiting for
        // the real network fetch needs a genuine delay first, then a bare
        // `pump()` to rebuild once that real data has actually arrived.
        await Future<void>.delayed(const Duration(milliseconds: 800));
        await tester.pump();

        for (final version in versions) {
          await tester.tap(find.byKey(Key('download_button_${version.id}')));
          // Generous: the first download of each version renders a fresh
          // PDF and uploads it to storage (Phase 4's cache-on-miss design),
          // which is slower than a cached re-fetch.
          await Future<void>.delayed(const Duration(seconds: 3));
          await tester.pump();
        }
      });
      await pumpBounded(tester);

      expect(downloaded.length, 3);

      // Every downloaded PDF must match a fresh direct download of the same
      // version from backend storage (byte-for-byte), and every version's
      // PDF must be distinct from every other version's.
      final directHashes = <String>{};
      await tester.runAsync(() async {
        for (final version in versions) {
          final direct = await api.downloadVersionPdf(version.id);
          final filename = 'Download test quiz_v${version.versionNumber}.pdf';
          expect(downloaded[filename], isNotNull);
          expect(
            sha256.convert(downloaded[filename]!).toString(),
            sha256.convert(direct).toString(),
          );
          directHashes.add(sha256.convert(direct).toString());
        }
      });
      expect(directHashes.length, 3, reason: 'each version PDF must have a distinct hash');
      api.close();
    });
  });
}
