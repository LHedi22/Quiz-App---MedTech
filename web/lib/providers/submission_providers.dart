import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/submission.dart';
import '../services/api_client.dart';
import 'api_providers.dart';

/// Holds one quiz's submissions and the currently-applied status filter.
/// [updateSubmissionLocally] applies a PATCH result to in-memory state
/// directly (rather than re-fetching), so the results dashboard reflects a
/// manual correction reactively - including dropping a submission out of a
/// status-filtered view the instant it's no longer in that status.
class QuizSubmissionsNotifier extends StateNotifier<AsyncValue<List<Submission>>> {
  final ApiClient _api;
  final String quizId;
  String? statusFilter;

  QuizSubmissionsNotifier(this._api, this.quizId) : super(const AsyncValue.loading()) {
    load();
  }

  Future<void> load({String? status}) async {
    statusFilter = status;
    state = const AsyncValue.loading();
    try {
      final subs = await _api.listQuizSubmissions(quizId, status: status);
      state = AsyncValue.data(subs);
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }

  void updateSubmissionLocally(Submission updated) {
    final current = state.valueOrNull;
    if (current == null) return;
    final matchesFilter = statusFilter == null || updated.status == statusFilter;
    final withoutOld = current.where((s) => s.id != updated.id).toList();
    state = AsyncValue.data(matchesFilter ? [...withoutOld, updated] : withoutOld);
  }
}

final quizSubmissionsProvider =
    StateNotifierProvider.family<QuizSubmissionsNotifier, AsyncValue<List<Submission>>, String>(
        (ref, quizId) {
  return QuizSubmissionsNotifier(ref.watch(apiClientProvider), quizId);
});

final submissionDetailProvider = FutureProvider.family<Submission, String>((ref, submissionId) {
  return ref.watch(apiClientProvider).getSubmission(submissionId);
});
