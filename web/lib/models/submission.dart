class Answer {
  final String id;
  final int questionNo;
  final String? detectedOption;
  final double confidence;
  final bool flagged;
  final bool? correct;
  final double? score;

  Answer({
    required this.id,
    required this.questionNo,
    required this.detectedOption,
    required this.confidence,
    required this.flagged,
    required this.correct,
    required this.score,
  });

  factory Answer.fromJson(Map<String, dynamic> json) => Answer(
        id: json['id'] as String,
        questionNo: json['question_no'] as int,
        detectedOption: json['detected_option'] as String?,
        confidence: (json['confidence'] as num).toDouble(),
        flagged: json['flagged'] as bool,
        correct: json['correct'] as bool?,
        score: (json['score'] as num?)?.toDouble(),
      );
}

class Submission {
  final String id;
  final String versionId;
  final String? studentId;
  final double? totalScore;
  final String status;
  final DateTime createdAt;
  final List<Answer> answers;

  Submission({
    required this.id,
    required this.versionId,
    required this.studentId,
    required this.totalScore,
    required this.status,
    required this.createdAt,
    this.answers = const [],
  });

  factory Submission.fromJson(Map<String, dynamic> json) => Submission(
        id: json['id'] as String,
        versionId: json['version_id'] as String,
        studentId: json['student_id'] as String?,
        totalScore: (json['total_score'] as num?)?.toDouble(),
        status: json['status'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
        answers: (json['answers'] as List<dynamic>?)
                ?.map((a) => Answer.fromJson(a as Map<String, dynamic>))
                .toList() ??
            const [],
      );

  Submission copyWith({String? status, double? totalScore, List<Answer>? answers}) => Submission(
        id: id,
        versionId: versionId,
        studentId: studentId,
        totalScore: totalScore ?? this.totalScore,
        status: status ?? this.status,
        createdAt: createdAt,
        answers: answers ?? this.answers,
      );
}
