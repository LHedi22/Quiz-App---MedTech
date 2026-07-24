/// Response shape of `POST /scan` (see backend/app/routers/scan.py) - the
/// pipeline result for one uploaded page image.
class ScanResult {
  final String submissionId;
  final String status; // pending | needs_review | finalized
  final double? totalScore;
  final List<int> flaggedQuestionNumbers;

  ScanResult({
    required this.submissionId,
    required this.status,
    required this.totalScore,
    required this.flaggedQuestionNumbers,
  });

  factory ScanResult.fromJson(Map<String, dynamic> json) => ScanResult(
        submissionId: json['submission_id'] as String,
        status: json['status'] as String,
        totalScore: (json['total_score'] as num?)?.toDouble(),
        flaggedQuestionNumbers: (json['flagged_question_numbers'] as List)
            .map((e) => e as int)
            .toList(),
      );
}

/// Response shape of `GET /submissions/{id}` - only the fields the mobile
/// app needs (status reconciliation for the batch summary screen).
class SubmissionStatus {
  final String id;
  final String status;
  final double? totalScore;

  SubmissionStatus({required this.id, required this.status, required this.totalScore});

  factory SubmissionStatus.fromJson(Map<String, dynamic> json) => SubmissionStatus(
        id: json['id'] as String,
        status: json['status'] as String,
        totalScore: (json['total_score'] as num?)?.toDouble(),
      );
}
