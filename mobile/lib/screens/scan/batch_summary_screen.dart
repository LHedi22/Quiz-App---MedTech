import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../models/batch_summary.dart';
import '../../providers/queue_providers.dart';

/// Post-scan summary (Subtask 8.4). Mobile never implements the flagged-
/// answer review UI itself (see CLAUDE.md's phase split) - this screen only
/// tallies and hands off to the web app.
class BatchSummaryScreen extends ConsumerWidget {
  const BatchSummaryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(queueControllerProvider);
    final summary = BatchSummary.fromItems(items);

    return Scaffold(
      appBar: AppBar(title: const Text('Batch summary')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Total scanned: ${summary.total}', key: const Key('summary_total')),
            const SizedBox(height: 8),
            Text('Finalized: ${summary.finalized}', key: const Key('summary_finalized')),
            Text('Needs review: ${summary.needsReview}', key: const Key('summary_needs_review')),
            Text('Pending sync: ${summary.pendingSync}', key: const Key('summary_pending')),
            Text('Failed uploads: ${summary.failed}', key: const Key('summary_failed')),
            const SizedBox(height: 24),
            const Text(
              'Flagged answers are reviewed on the web app, not here - '
              'sign in to the professor dashboard to finalize this batch.',
              key: Key('web_handoff_text'),
            ),
            const Spacer(),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    key: const Key('sync_now_button'),
                    onPressed: () => ref.read(queueControllerProvider.notifier).syncNow(),
                    child: const Text('Sync now'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton(
                    key: const Key('start_new_batch_button'),
                    onPressed: () {
                      ref.read(queueControllerProvider.notifier).clearBatch();
                      context.go('/scan');
                    },
                    child: const Text('Start new batch'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
