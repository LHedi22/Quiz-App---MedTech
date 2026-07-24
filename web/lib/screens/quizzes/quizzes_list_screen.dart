import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../providers/quiz_providers.dart';

class QuizzesListScreen extends ConsumerWidget {
  const QuizzesListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final quizzesAsync = ref.watch(quizzesProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Quizzes')),
      floatingActionButton: FloatingActionButton(
        key: const Key('create_quiz_fab'),
        onPressed: () => context.go('/quizzes/create'),
        child: const Icon(Icons.add),
      ),
      body: quizzesAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, st) => Center(child: Text('Failed to load quizzes: $err')),
        data: (quizzes) {
          if (quizzes.isEmpty) {
            return const Center(child: Text('No quizzes yet. Tap + to create one.'));
          }
          return ListView.builder(
            itemCount: quizzes.length,
            itemBuilder: (context, index) {
              final quiz = quizzes[index];
              return ListTile(
                key: Key('quiz_tile_${quiz.id}'),
                title: Text(quiz.title),
                subtitle: Text(DateFormat.yMMMd().add_jm().format(quiz.createdAt)),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => context.go('/quizzes/${quiz.id}/versions?title=${quiz.title}'),
              );
            },
          );
        },
      ),
    );
  }
}
