import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

enum QueueItemState { pending, uploading, processed, failed }

String generateQueueItemId() {
  final rand = Random();
  return '${DateTime.now().microsecondsSinceEpoch}-${rand.nextInt(1 << 32)}';
}

/// One captured page, queued locally until it's successfully POSTed to
/// `/scan` (see Subtask 8.3). Persisted as JSON via [QueueRepository] -
/// image bytes travel as base64 in the same record rather than a separate
/// file, so the whole queue is one atomic read/write and there's no
/// path_provider/platform-channel dependency for file storage.
class ScanQueueItem {
  final String id;
  final Uint8List imageBytes;
  final String? studentId;
  final DateTime createdAt;
  final QueueItemState state;
  final int retryCount;
  final DateTime? nextAttemptAt;
  final String? lastError;
  final String? submissionId;
  final String? resultStatus;
  final double? totalScore;

  ScanQueueItem({
    required this.id,
    required this.imageBytes,
    this.studentId,
    required this.createdAt,
    this.state = QueueItemState.pending,
    this.retryCount = 0,
    this.nextAttemptAt,
    this.lastError,
    this.submissionId,
    this.resultStatus,
    this.totalScore,
  });

  ScanQueueItem copyWith({
    QueueItemState? state,
    int? retryCount,
    DateTime? nextAttemptAt,
    bool clearNextAttemptAt = false,
    String? lastError,
    bool clearLastError = false,
    String? submissionId,
    String? resultStatus,
    double? totalScore,
  }) =>
      ScanQueueItem(
        id: id,
        imageBytes: imageBytes,
        studentId: studentId,
        createdAt: createdAt,
        state: state ?? this.state,
        retryCount: retryCount ?? this.retryCount,
        nextAttemptAt: clearNextAttemptAt ? null : (nextAttemptAt ?? this.nextAttemptAt),
        lastError: clearLastError ? null : (lastError ?? this.lastError),
        submissionId: submissionId ?? this.submissionId,
        resultStatus: resultStatus ?? this.resultStatus,
        totalScore: totalScore ?? this.totalScore,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'image_bytes_b64': base64Encode(imageBytes),
        'student_id': studentId,
        'created_at': createdAt.toIso8601String(),
        'state': state.name,
        'retry_count': retryCount,
        'next_attempt_at': nextAttemptAt?.toIso8601String(),
        'last_error': lastError,
        'submission_id': submissionId,
        'result_status': resultStatus,
        'total_score': totalScore,
      };

  factory ScanQueueItem.fromJson(Map<String, dynamic> json) => ScanQueueItem(
        id: json['id'] as String,
        imageBytes: base64Decode(json['image_bytes_b64'] as String),
        studentId: json['student_id'] as String?,
        createdAt: DateTime.parse(json['created_at'] as String),
        state: QueueItemState.values.byName(json['state'] as String),
        retryCount: json['retry_count'] as int,
        nextAttemptAt: json['next_attempt_at'] == null
            ? null
            : DateTime.parse(json['next_attempt_at'] as String),
        lastError: json['last_error'] as String?,
        submissionId: json['submission_id'] as String?,
        resultStatus: json['result_status'] as String?,
        totalScore: (json['total_score'] as num?)?.toDouble(),
      );
}
