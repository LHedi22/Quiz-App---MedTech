import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'config.dart';
import 'providers/queue_providers.dart';
import 'router/app_router.dart';
import 'services/api_client.dart';
import 'services/queue_repository.dart';
import 'services/sync_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Supabase.initialize(
    url: AppConfig.supabaseUrl,
    publishableKey: AppConfig.supabasePublishableKey,
  );

  final repository = QueueRepository(await SharedPreferences.getInstance());
  final apiClient = ApiClient();
  final connectivityStream = Connectivity()
      .onConnectivityChanged
      .map((results) => results.any((r) => r != ConnectivityResult.none));
  final syncService = SyncService(
    repository: repository,
    api: apiClient,
    connectivityStream: connectivityStream,
  );

  runApp(ProviderScope(
    overrides: [
      apiClientProvider.overrideWithValue(apiClient),
      queueRepositoryProvider.overrideWithValue(repository),
      syncServiceProvider.overrideWithValue(syncService),
    ],
    child: const ExamScannerApp(),
  ));
}

class ExamScannerApp extends ConsumerWidget {
  const ExamScannerApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'Exam Scanner',
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo)),
      routerConfig: router,
    );
  }
}
