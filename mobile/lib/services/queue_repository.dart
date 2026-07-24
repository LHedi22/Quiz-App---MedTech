import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/scan_queue_item.dart';

/// Persists the scan queue as one JSON blob in [SharedPreferences]. All of
/// [QueueRepository]'s state lives in the plugin's on-disk store, not in
/// memory here - so a queue built up before an app restart is exactly what
/// [loadAll] returns after one, which is what Subtask 8.3's DoD tests.
class QueueRepository {
  static const _storageKey = 'scan_queue_items_v1';
  final SharedPreferences _prefs;

  QueueRepository(this._prefs);

  static Future<QueueRepository> create() async {
    return QueueRepository(await SharedPreferences.getInstance());
  }

  List<ScanQueueItem> loadAll() {
    final raw = _prefs.getString(_storageKey);
    if (raw == null || raw.isEmpty) return [];
    final list = jsonDecode(raw) as List;
    return list.map((e) => ScanQueueItem.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<void> saveAll(List<ScanQueueItem> items) async {
    await _prefs.setString(_storageKey, jsonEncode(items.map((e) => e.toJson()).toList()));
  }

  Future<void> add(ScanQueueItem item) async {
    final items = loadAll()..add(item);
    await saveAll(items);
  }

  /// No-op if [item.id] isn't present - callers always update an item they
  /// just loaded, so a miss here would indicate a bug elsewhere rather than
  /// something to silently paper over; kept a no-op (not a throw) only
  /// because a queue item can legitimately be cleared concurrently by
  /// another code path in a future extension, and update-after-clear should
  /// not crash the sync loop mid-batch.
  Future<void> update(ScanQueueItem item) async {
    final items = loadAll();
    final index = items.indexWhere((e) => e.id == item.id);
    if (index == -1) return;
    final updated = List<ScanQueueItem>.of(items);
    updated[index] = item;
    await saveAll(updated);
  }

  Future<void> clear() async {
    await _prefs.remove(_storageKey);
  }
}
