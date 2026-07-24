import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:exam_scanner_mobile/models/batch_summary.dart';
import 'package:exam_scanner_mobile/models/scan_queue_item.dart';

ScanQueueItem _item(String id, QueueItemState state, {String? resultStatus}) => ScanQueueItem(
      id: id,
      imageBytes: Uint8List(0),
      createdAt: DateTime.now(),
      state: state,
      resultStatus: resultStatus,
    );

void main() {
  test('tallies mixed-status items exactly', () {
    final items = [
      _item('a', QueueItemState.processed, resultStatus: 'finalized'),
      _item('b', QueueItemState.processed, resultStatus: 'finalized'),
      _item('c', QueueItemState.processed, resultStatus: 'needs_review'),
      _item('d', QueueItemState.pending),
      _item('e', QueueItemState.uploading),
      _item('f', QueueItemState.failed),
    ];

    final summary = BatchSummary.fromItems(items);

    expect(summary.total, 6);
    expect(summary.finalized, 2);
    expect(summary.needsReview, 1);
    expect(summary.pendingSync, 2);
    expect(summary.failed, 1);
  });

  test('empty queue tallies to all zeros', () {
    final summary = BatchSummary.fromItems([]);
    expect(summary.total, 0);
    expect(summary.finalized, 0);
    expect(summary.needsReview, 0);
    expect(summary.pendingSync, 0);
    expect(summary.failed, 0);
  });
}
