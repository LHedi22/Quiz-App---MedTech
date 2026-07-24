import 'dart:async';

import '../models/scan_queue_item.dart';
import 'api_client.dart';
import 'queue_repository.dart';

/// Drains the local scan queue against [ScanApi], with exponential backoff
/// on failure (Subtask 8.3). Two triggers call [syncPending]: the app after
/// every new capture, and - if a [connectivityStream] is supplied - a
/// transition to "online".
///
/// [connectivityStream] is injected rather than read from `connectivity_plus`
/// directly so tests can simulate reconnection with a plain
/// `StreamController<bool>` instead of needing a real platform channel/device
/// (this dev environment has neither, see PROGRESS.md Phase 0 notes); the
/// real app wires the actual connectivity stream in at construction time
/// (see providers/queue_providers.dart).
class SyncService {
  final QueueRepository repository;
  final ScanApi api;
  final Duration baseBackoff;
  final Duration maxBackoff;

  StreamSubscription<bool>? _connectivitySubscription;
  bool _syncing = false;

  SyncService({
    required this.repository,
    required this.api,
    Stream<bool>? connectivityStream,
    this.baseBackoff = const Duration(seconds: 2),
    this.maxBackoff = const Duration(minutes: 5),
  }) {
    _connectivitySubscription = connectivityStream?.listen((online) {
      if (online) unawaited(syncPending());
    });
  }

  void dispose() {
    _connectivitySubscription?.cancel();
  }

  /// Exponential backoff capped at [maxBackoff]: 2s, 4s, 8s, 16s, ... A
  /// failed item is never dropped - it just becomes eligible for its next
  /// attempt further and further in the future, per Subtask 8.3's DoD.
  Duration backoffFor(int retryCount) {
    final uncapped = baseBackoff * (1 << retryCount.clamp(0, 10));
    return uncapped > maxBackoff ? maxBackoff : uncapped;
  }

  bool _isEligible(ScanQueueItem item, DateTime now) {
    if (item.state == QueueItemState.pending) return true;
    if (item.state != QueueItemState.failed) return false;
    return item.nextAttemptAt == null || !item.nextAttemptAt!.isAfter(now);
  }

  /// Re-entrancy guarded: a capture-triggered call and a connectivity-
  /// triggered call can race, and running two passes over the same queue
  /// concurrently would double-attempt whatever is currently eligible.
  Future<void> syncPending() async {
    if (_syncing) return;
    _syncing = true;
    try {
      final now = DateTime.now();
      for (final item in repository.loadAll()) {
        if (_isEligible(item, now)) {
          await _attempt(item);
        }
      }
    } finally {
      _syncing = false;
    }
  }

  Future<void> _attempt(ScanQueueItem item) async {
    await repository.update(item.copyWith(state: QueueItemState.uploading));
    try {
      final result = await api.scanSubmission(item.imageBytes, studentId: item.studentId);
      await repository.update(item.copyWith(
        state: QueueItemState.processed,
        submissionId: result.submissionId,
        resultStatus: result.status,
        totalScore: result.totalScore,
        clearLastError: true,
        clearNextAttemptAt: true,
      ));
    } catch (error) {
      final retryCount = item.retryCount + 1;
      await repository.update(item.copyWith(
        state: QueueItemState.failed,
        retryCount: retryCount,
        nextAttemptAt: DateTime.now().add(backoffFor(retryCount)),
        lastError: error.toString(),
      ));
    }
  }
}
