import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../models/submission.dart';
import '../../providers/api_providers.dart';
import '../../providers/submission_providers.dart';

const _optionLabels = ['A', 'B', 'C', 'D'];

/// Subtask 7.5: for a needs_review submission, show each flagged question
/// with the detected result and a control to manually select the correct
/// option; PATCHes on submit and updates reactively with no page refresh.
class SubmissionReviewScreen extends ConsumerStatefulWidget {
  final String submissionId;
  final String? quizId;
  const SubmissionReviewScreen({super.key, required this.submissionId, this.quizId});

  @override
  ConsumerState<SubmissionReviewScreen> createState() => _SubmissionReviewScreenState();
}

class _SubmissionReviewScreenState extends ConsumerState<SubmissionReviewScreen> {
  Submission? _submission;
  final Map<String, String> _selectedOption = {};
  final Set<String> _saving = {};
  String? _error;

  void _applyUpdatedSubmission(Submission updated) {
    setState(() => _submission = updated);
    final quizId = widget.quizId;
    if (quizId != null) {
      ref.read(quizSubmissionsProvider(quizId).notifier).updateSubmissionLocally(updated);
    }
  }

  Future<void> _saveCorrection(Answer answer) async {
    final selected = _selectedOption[answer.id];
    if (selected == null) return;
    setState(() {
      _saving.add(answer.id);
      _error = null;
    });
    try {
      final updated = await ref
          .read(apiClientProvider)
          .correctAnswer(widget.submissionId, answer.id, selected);
      _applyUpdatedSubmission(updated);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _saving.remove(answer.id));
    }
  }

  @override
  Widget build(BuildContext context) {
    final detailAsync = ref.watch(submissionDetailProvider(widget.submissionId));

    return Scaffold(
      appBar: AppBar(title: const Text('Review flagged answers')),
      body: _submission != null
          ? _buildBody(context, _submission!)
          : detailAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (err, st) => Center(child: Text('Failed to load submission: $err')),
              data: (submission) {
                // Seed local reactive state once; subsequent rebuilds use
                // `_submission` (updated in place by each correction) rather
                // than this future, which never re-fires.
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  if (mounted && _submission == null) setState(() => _submission = submission);
                });
                return _buildBody(context, submission);
              },
            ),
    );
  }

  Widget _buildBody(BuildContext context, Submission submission) {
    final flagged = submission.answers.where((a) => a.flagged).toList();

    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Status: ${submission.status}', key: const Key('submission_status')),
          const SizedBox(height: 8),
          Text('Total score: ${submission.totalScore?.toStringAsFixed(1) ?? '-'}'),
          const SizedBox(height: 24),
          if (submission.status != 'needs_review')
            const Text('All flagged answers resolved — this submission is no longer needs_review.')
          else ...[
            Text('${flagged.length} flagged question(s) remaining:',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            for (final answer in flagged) _FlaggedAnswerRow(
              answer: answer,
              selected: _selectedOption[answer.id],
              saving: _saving.contains(answer.id),
              onSelect: (option) => setState(() => _selectedOption[answer.id] = option),
              onSave: () => _saveCorrection(answer),
            ),
          ],
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 16),
              child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          const SizedBox(height: 24),
          TextButton(
            onPressed: () => context.pop(),
            child: const Text('Back to results'),
          ),
        ],
      ),
    );
  }
}

class _FlaggedAnswerRow extends StatelessWidget {
  final Answer answer;
  final String? selected;
  final bool saving;
  final ValueChanged<String> onSelect;
  final VoidCallback onSave;

  const _FlaggedAnswerRow({
    required this.answer,
    required this.selected,
    required this.saving,
    required this.onSelect,
    required this.onSave,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      key: Key('flagged_answer_${answer.id}'),
      margin: const EdgeInsets.symmetric(vertical: 8),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Expanded(
              child: Text(
                'Question ${answer.questionNo} — detected: '
                '${answer.detectedOption ?? 'none'} (confidence ${answer.confidence.toStringAsFixed(2)})',
              ),
            ),
            DropdownButton<String>(
              key: Key('correct_option_dropdown_${answer.id}'),
              hint: const Text('Correct option'),
              value: selected,
              items: [
                for (final label in _optionLabels) DropdownMenuItem(value: label, child: Text(label)),
              ],
              onChanged: (value) {
                if (value != null) onSelect(value);
              },
            ),
            const SizedBox(width: 16),
            ElevatedButton(
              key: Key('save_correction_button_${answer.id}'),
              onPressed: (selected == null || saving) ? null : onSave,
              child: saving
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Save'),
            ),
          ],
        ),
      ),
    );
  }
}
