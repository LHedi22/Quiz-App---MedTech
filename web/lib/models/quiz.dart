class Quiz {
  final String id;
  final String title;
  final DateTime createdAt;

  Quiz({required this.id, required this.title, required this.createdAt});

  factory Quiz.fromJson(Map<String, dynamic> json) => Quiz(
        id: json['id'] as String,
        title: json['title'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
      );
}

class QuizVersion {
  final String id;
  final int versionNumber;

  QuizVersion({required this.id, required this.versionNumber});

  factory QuizVersion.fromJson(Map<String, dynamic> json) => QuizVersion(
        id: json['id'] as String,
        versionNumber: json['version_number'] as int,
      );
}

/// One bad row from Phase 2's structured Excel validation error, e.g.
/// `{"row_number": 3, "messages": ["correct_option must be exactly one of A/B/C/D, got ''"]}`.
class RowError {
  final int rowNumber;
  final List<String> messages;

  RowError({required this.rowNumber, required this.messages});

  factory RowError.fromJson(Map<String, dynamic> json) => RowError(
        rowNumber: json['row_number'] as int,
        messages: (json['messages'] as List).cast<String>(),
      );
}
