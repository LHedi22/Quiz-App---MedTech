import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/scan_queue_item.dart';
import '../services/api_client.dart';
import '../services/queue_repository.dart';
import '../services/sync_service.dart';

/// These three are constructed once in `main()` (SharedPreferences init is
/// async, same as `Supabase.initialize`) and injected via `ProviderScope`
/// overrides - mirrors web/lib/main.dart's pattern of doing async setup
/// before `runApp` rather than threading `FutureProvider`s through every
/// consumer.
final apiClientProvider = Provider<ScanApi>((ref) {
  throw UnimplementedError('apiClientProvider must be overridden in main()');
});

final queueRepositoryProvider = Provider<QueueRepository>((ref) {
  throw UnimplementedError('queueRepositoryProvider must be overridden in main()');
});

final syncServiceProvider = Provider<SyncService>((ref) {
  throw UnimplementedError('syncServiceProvider must be overridden in main()');
});

/// Drives the scan queue for the UI: [addCapture] persists a new item and
/// kicks off a sync attempt; [state] always mirrors [QueueRepository]'s
/// on-disk contents so the batch summary screen (Subtask 8.4) reads exactly
/// what will survive an app restart.
class QueueController extends StateNotifier<List<ScanQueueItem>> {
  final QueueRepository repository;
  final SyncService syncService;

  QueueController(this.repository, this.syncService) : super(repository.loadAll());

  void refresh() {
    state = repository.loadAll();
  }

  Future<void> addCapture(Uint8List imageBytes, {String? studentId}) async {
    final item = ScanQueueItem(
      id: generateQueueItemId(),
      imageBytes: imageBytes,
      studentId: studentId,
      createdAt: DateTime.now(),
    );
    await repository.add(item);
    refresh();
    await syncNow();
  }

  Future<void> syncNow() async {
    await syncService.syncPending();
    refresh();
  }

  /// Discards every queue item - used once a batch has been handed off via
  /// the summary screen, so the next scanning session starts empty.
  Future<void> clearBatch() async {
    await repository.clear();
    refresh();
  }
}

final queueControllerProvider =
    StateNotifierProvider<QueueController, List<ScanQueueItem>>((ref) {
  return QueueController(ref.watch(queueRepositoryProvider), ref.watch(syncServiceProvider));
});
