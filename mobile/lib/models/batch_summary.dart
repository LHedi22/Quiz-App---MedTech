import 'scan_queue_item.dart';

/// Pure tally over the local queue, kept separate from any widget so
/// Subtask 8.4's DoD (exact counts vs. real backend state) can be verified
/// without building UI - see test/models/batch_summary_test.dart.
class BatchSummary {
  final int total;
  final int finalized;
  final int needsReview;
  final int pendingSync;
  final int failed;

  const BatchSummary({
    required this.total,
    required this.finalized,
    required this.needsReview,
    required this.pendingSync,
    required this.failed,
  });

  factory BatchSummary.fromItems(List<ScanQueueItem> items) {
    var finalized = 0;
    var needsReview = 0;
    var pendingSync = 0;
    var failed = 0;
    for (final item in items) {
      switch (item.state) {
        case QueueItemState.processed:
          switch (item.resultStatus) {
            case 'finalized':
              finalized++;
              break;
            case 'needs_review':
              needsReview++;
              break;
            default:
              // Backend returned 'pending' (see backend/app/services/scoring.py
              // _status_for) - not yet a terminal state either way.
              pendingSync++;
          }
          break;
        case QueueItemState.failed:
          failed++;
          break;
        case QueueItemState.pending:
        case QueueItemState.uploading:
          pendingSync++;
          break;
      }
    }
    return BatchSummary(
      total: items.length,
      finalized: finalized,
      needsReview: needsReview,
      pendingSync: pendingSync,
      failed: failed,
    );
  }
}
