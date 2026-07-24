import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:exam_scanner_mobile/models/scan_queue_item.dart';
import 'package:exam_scanner_mobile/services/queue_repository.dart';

ScanQueueItem _item(String id) => ScanQueueItem(
      id: id,
      imageBytes: Uint8List.fromList([1, 2, 3]),
      createdAt: DateTime(2026, 1, 1),
    );

void main() {
  setUp(() {
    // Fresh in-memory backing store per test - shared_preferences' test
    // implementation is a single static in-memory map, so without this a
    // previous test's queue would leak into the next one.
    SharedPreferences.setMockInitialValues({});
  });

  test('queue persists across an app restart (a new repository instance sees prior writes)', () async {
    final firstInstance = QueueRepository(await SharedPreferences.getInstance());
    await firstInstance.add(_item('a'));
    await firstInstance.add(_item('b'));

    // A fresh repository backed by a fresh SharedPreferences handle - this
    // is what "app restart" looks like: nothing kept in Dart memory, only
    // whatever shared_preferences itself persisted.
    final afterRestart = QueueRepository(await SharedPreferences.getInstance());
    final items = afterRestart.loadAll();

    expect(items.map((e) => e.id), containsAll(['a', 'b']));
    expect(items, hasLength(2));
  });

  test('update() persists a state change that a fresh instance can see', () async {
    final repository = QueueRepository(await SharedPreferences.getInstance());
    await repository.add(_item('a'));

    final loaded = repository.loadAll().single;
    await repository.update(loaded.copyWith(state: QueueItemState.processed, resultStatus: 'finalized'));

    final afterRestart = QueueRepository(await SharedPreferences.getInstance());
    final reloaded = afterRestart.loadAll().single;
    expect(reloaded.state, QueueItemState.processed);
    expect(reloaded.resultStatus, 'finalized');
  });

  test('no data loss: image bytes round-trip exactly through persistence', () async {
    final bytes = Uint8List.fromList(List.generate(500, (i) => i % 256));
    final repository = QueueRepository(await SharedPreferences.getInstance());
    await repository.add(ScanQueueItem(id: 'a', imageBytes: bytes, createdAt: DateTime(2026, 1, 1)));

    final afterRestart = QueueRepository(await SharedPreferences.getInstance());
    expect(afterRestart.loadAll().single.imageBytes, equals(bytes));
  });
}
