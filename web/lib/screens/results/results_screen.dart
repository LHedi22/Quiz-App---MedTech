import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../models/submission.dart';
import '../../providers/quiz_providers.dart';
import '../../providers/submission_providers.dart';

const _statusFilters = [null, 'pending', 'needs_review', 'finalized'];

/// Subtask 7.4: list submissions per quiz with status/score/timestamp,
/// filter/sort by status.
class ResultsScreen extends ConsumerStatefulWidget {
  const ResultsScreen({super.key});

  @override
  ConsumerState<ResultsScreen> createState() => _ResultsScreenState();
}

class _ResultsScreenState extends ConsumerState<ResultsScreen> {
  String? _selectedQuizId;
  String? _statusFilter;
  bool _sortNewestFirst = true;

  @override
  Widget build(BuildContext context) {
    final quizzesAsync = ref.watch(quizzesProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Results')),
      body: quizzesAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) => Center(child: Text('Failed to load quizzes: $err')),
        data: (quizzes) {
          if (quizzes.isEmpty) {
            return const Center(child: Text('No quizzes yet.'));
          }
          _selectedQuizId ??= quizzes.first.id;

          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    DropdownButton<String>(
                      key: const Key('quiz_selector'),
                      value: _selectedQuizId,
                      items: [
                        for (final quiz in quizzes)
                          DropdownMenuItem(value: quiz.id, child: Text(quiz.title)),
                      ],
                      onChanged: (value) => setState(() => _selectedQuizId = value),
                    ),
                    const SizedBox(width: 24),
                    DropdownButton<String?>(
                      key: const Key('status_filter'),
                      value: _statusFilter,
                      items: [
                        for (final status in _statusFilters)
                          DropdownMenuItem(value: status, child: Text(status ?? 'All statuses')),
                      ],
                      onChanged: (value) {
                        setState(() => _statusFilter = value);
                        ref
                            .read(quizSubmissionsProvider(_selectedQuizId!).notifier)
                            .load(status: value);
                      },
                    ),
                    const SizedBox(width: 24),
                    IconButton(
                      key: const Key('sort_toggle_button'),
                      icon: Icon(_sortNewestFirst ? Icons.arrow_downward : Icons.arrow_upward),
                      tooltip: 'Sort by time',
                      onPressed: () => setState(() => _sortNewestFirst = !_sortNewestFirst),
                    ),
                  ],
                ),
              ),
              Expanded(child: _SubmissionsList(
                quizId: _selectedQuizId!,
                sortNewestFirst: _sortNewestFirst,
              )),
            ],
          );
        },
      ),
    );
  }
}

class _SubmissionsList extends ConsumerWidget {
  final String quizId;
  final bool sortNewestFirst;
  const _SubmissionsList({required this.quizId, required this.sortNewestFirst});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final submissionsAsync = ref.watch(quizSubmissionsProvider(quizId));

    return submissionsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (err, st) => Center(child: Text('Failed to load submissions: $err')),
      data: (submissions) {
        if (submissions.isEmpty) {
          return const Center(child: Text('No submissions for this filter.'));
        }
        final sorted = [...submissions]..sort(
            (a, b) => sortNewestFirst
                ? b.createdAt.compareTo(a.createdAt)
                : a.createdAt.compareTo(b.createdAt),
          );
        return ListView.builder(
          itemCount: sorted.length,
          itemBuilder: (context, index) => _SubmissionRow(submission: sorted[index], quizId: quizId),
        );
      },
    );
  }
}

class _SubmissionRow extends StatelessWidget {
  final Submission submission;
  final String quizId;
  const _SubmissionRow({required this.submission, required this.quizId});

  @override
  Widget build(BuildContext context) {
    return ListTile(
      key: Key('submission_row_${submission.id}'),
      title: Text('Status: ${submission.status}'),
      subtitle: Text(
        'Score: ${submission.totalScore?.toStringAsFixed(1) ?? '-'}  •  '
        '${DateFormat.yMMMd().add_jm().format(submission.createdAt)}',
      ),
      trailing: submission.status == 'needs_review'
          ? TextButton(
              key: Key('review_button_${submission.id}'),
              onPressed: () => context.go('/submissions/${submission.id}/review?quiz=$quizId'),
              child: const Text('Review'),
            )
          : null,
    );
  }
}
