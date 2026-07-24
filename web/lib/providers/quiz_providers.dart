import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/quiz.dart';
import '../services/api_client.dart';
import 'api_providers.dart';

class QuizzesNotifier extends StateNotifier<AsyncValue<List<Quiz>>> {
  final ApiClient _api;
  QuizzesNotifier(this._api) : super(const AsyncValue.loading()) {
    load();
  }

  Future<void> load() async {
    state = const AsyncValue.loading();
    try {
      final quizzes = await _api.listQuizzes();
      state = AsyncValue.data(quizzes);
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }

  Future<Quiz> create(String title) async {
    final quiz = await _api.createQuiz(title);
    state.whenData((quizzes) => state = AsyncValue.data([quiz, ...quizzes]));
    return quiz;
  }
}

final quizzesProvider = StateNotifierProvider<QuizzesNotifier, AsyncValue<List<Quiz>>>((ref) {
  return QuizzesNotifier(ref.watch(apiClientProvider));
});

final quizVersionsProvider = FutureProvider.family<List<QuizVersion>, String>((ref, quizId) {
  return ref.watch(apiClientProvider).listVersions(quizId);
});
