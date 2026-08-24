import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:exam_scanner_mobile/models/scan_queue_item.dart';
import 'package:exam_scanner_mobile/models/scan_result.dart';
import 'package:exam_scanner_mobile/services/api_client.dart';
import 'package:exam_scanner_mobile/services/queue_repository.dart';
import 'package:exam_scanner_mobile/services/sync_service.dart';

/// Records exactly what it's told to do, in order - lets tests simulate a
/// backend error on one attempt and success on the next without touching a
/// real network (see test/scan/batch_summary_backend_test.dart for the
/// counterpart real-network coverage).
class FakeScanApi implements ScanApi {
  final List<Object> _behaviors = [];
  int callCount = 0;
  final List<String> receivedCaptureIds = [];

  void enqueueSuccess(ScanResult result) => _behaviors.add(result);
  void enqueueFailure(Object error) => _behaviors.add(error);

  @override
  Future<ScanResult> scanSubmission(
    Uint8List imageBytes, {
    String? studentId,
    required String captureId,
  }) async {
    callCount++;
    receivedCaptureIds.add(captureId);
    if (_behaviors.isEmpty) {
      throw StateError('FakeScanApi.scanSubmission called with no behavior queued');
    }
    final behavior = _behaviors.removeAt(0);
    if (behavior is ScanResult) return behavior;
    throw behavior;
  }

  @override
  Future<SubmissionStatus> getSubmissionStatus(String submissionId) async {
    throw UnimplementedError('not needed by these tests');
  }
}

ScanQueueItem _pendingItem(String id) => ScanQueueItem(
      id: id,
      imageBytes: Uint8List.fromList([9, 9, 9]),
      createdAt: DateTime.now(),
    );

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('offline capture stays queued (pending) and does not require the network', () async {
    final repository = QueueRepository(await SharedPreferences.getInstance());
    await repository.add(_pendingItem('a'));

    // No sync was ever invoked - the item sits queued, and the app (via the
    // repository) can still read it back.
    expect(repository.loadAll().single.state, QueueItemState.pending);
  });

  test('a successful sync marks the item processed with the backend result', () async {
    final repository = QueueRepository(await SharedPreferences.getInstance());
    await repository.add(_pendingItem('a'));
    final api = FakeScanApi()
      ..enqueueSuccess(ScanResult(
        submissionId: 'sub-1',
        status: 'needs_review',
        totalScore: null,
        flaggedQuestionNumbers: [3],
      ));
    final syncService = SyncService(repository: repository, api: api);

    await syncService.syncPending();

    final item = repository.loadAll().single;
    expect(item.state, QueueItemState.processed);
    expect(item.submissionId, 'sub-1');
    expect(item.resultStatus, 'needs_review');
    expect(api.callCount, 1);
  });

  test('a failed upload retries with backoff instead of being dropped', () async {
    final repository = QueueRepository(await SharedPreferences.getInstance());
    await repository.add(_pendingItem('a'));
    final api = FakeScanApi()..enqueueFailure(ApiException(500, 'backend error'));
    final syncService = SyncService(repository: repository, api: api);

    await syncService.syncPending();

    var item = repository.loadAll().single;
    expect(item.state, QueueItemState.failed, reason: 'must not silently drop the item');
    expect(item.retryCount, 1);
    expect(item.nextAttemptAt, isNotNull);
    expect(item.nextAttemptAt!.isAfter(DateTime.now()), isTrue, reason: 'must back off, not retry immediately');
    expect(api.callCount, 1);

    // A second sync pass before the backoff window elapses must skip the
    // item entirely - this is what "not silently dropping" fails to catch
    // if only the counters above are checked.
    await syncService.syncPending();
    expect(api.callCount, 1, reason: 'not yet eligible for retry');

    // Simulate the backoff window having elapsed, then retry again: still
    // present, still retried (not dropped after repeated failure), and the
    // backoff grows.
    item = repository.loadAll().single;
    await repository.update(item.copyWith(nextAttemptAt: DateTime.now().subtract(const Duration(seconds: 1))));
    api.enqueueFailure(ApiException(500, 'backend error again'));
    await syncService.syncPending();

    item = repository.loadAll().single;
    expect(item.state, QueueItemState.failed);
    expect(item.retryCount, 2);
    expect(api.callCount, 2);
    expect(syncService.backoffFor(2), greaterThan(syncService.backoffFor(1)),
        reason: 'backoff must grow with each successive failure');
  });

  test('a retry after a failed attempt sends the same capture_id (item.id) both times', () async {
    // The backend dedupes on capture_id (0005_scan_capture_id migration) -
    // a retry after a lost response must reuse the id from the original
    // attempt, not a fresh one, or a request that actually succeeded
    // server-side despite the client seeing a failure would create a
    // duplicate submission on retry.
    final repository = QueueRepository(await SharedPreferences.getInstance());
    await repository.add(_pendingItem('stable-item-id'));
    final api = FakeScanApi()
      ..enqueueFailure(ApiException(500, 'backend error'))
      ..enqueueSuccess(ScanResult(submissionId: 's1', status: 'finalized', totalScore: 5, flaggedQuestionNumbers: []));
    final syncService = SyncService(repository: repository, api: api);

    await syncService.syncPending();
    final item = repository.loadAll().single;
    await repository.update(item.copyWith(nextAttemptAt: DateTime.now().subtract(const Duration(seconds: 1))));
    await syncService.syncPending();

    expect(api.receivedCaptureIds, ['stable-item-id', 'stable-item-id']);
  });

  test('backoff is capped at maxBackoff, not unbounded', () async {
    final syncService = SyncService(
      repository: QueueRepository(await SharedPreferences.getInstance()),
      api: FakeScanApi(),
      maxBackoff: const Duration(seconds: 30),
    );
    expect(syncService.backoffFor(20), const Duration(seconds: 30));
  });

  test('reconnection (connectivity stream emits online) auto-drains the queue without user action', () async {
    final repository = QueueRepository(await SharedPreferences.getInstance());
    await repository.add(_pendingItem('a'));
    await repository.add(_pendingItem('b'));
    final api = FakeScanApi()
      ..enqueueSuccess(ScanResult(submissionId: 's1', status: 'finalized', totalScore: 5, flaggedQuestionNumbers: []))
      ..enqueueSuccess(ScanResult(submissionId: 's2', status: 'finalized', totalScore: 5, flaggedQuestionNumbers: []));

    final connectivity = StreamController<bool>();
    final syncService = SyncService(repository: repository, api: api, connectivityStream: connectivity.stream);
    addTearDown(() {
      syncService.dispose();
      connectivity.close();
    });

    // Still offline: nothing attempted yet.
    expect(repository.loadAll().every((e) => e.state == QueueItemState.pending), isTrue);

    connectivity.add(true);
    // The listener's syncPending() call isn't awaited by the emitter -
    // give the fake (network-free, so effectively synchronous-ish) work a
    // moment to complete.
    await Future<void>.delayed(const Duration(milliseconds: 100));

    final items = repository.loadAll();
    expect(items.every((e) => e.state == QueueItemState.processed), isTrue,
        reason: 'reconnection must drain the queue automatically, with no explicit sync call from the test');
    expect(api.callCount, 2);
  });
}
