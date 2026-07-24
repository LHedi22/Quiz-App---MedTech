import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../models/quiz.dart';
import '../../providers/api_providers.dart';
import '../../providers/quiz_providers.dart';
import '../../services/api_client.dart';

class PickedExcelFile {
  final Uint8List bytes;
  final String filename;
  PickedExcelFile(this.bytes, this.filename);
}

typedef FilePickerFn = Future<PickedExcelFile?> Function();

Future<PickedExcelFile?> _defaultPickFile() async {
  final result = await FilePicker.platform.pickFiles(
    type: FileType.custom,
    allowedExtensions: ['xlsx'],
    withData: true,
  );
  if (result == null || result.files.isEmpty || result.files.single.bytes == null) return null;
  final file = result.files.single;
  return PickedExcelFile(file.bytes!, file.name);
}

/// Screen: create quiz (title) -> upload Excel -> show parsed questions for
/// confirmation / validation errors -> choose version count -> generate.
///
/// [pickFile] is injectable so widget tests can drive the real upload/error
/// path with fixture bytes without going through a native file dialog.
class QuizCreateScreen extends ConsumerStatefulWidget {
  final FilePickerFn pickFile;
  const QuizCreateScreen({super.key, this.pickFile = _defaultPickFile});

  @override
  ConsumerState<QuizCreateScreen> createState() => _QuizCreateScreenState();
}

class _QuizCreateScreenState extends ConsumerState<QuizCreateScreen> {
  final _titleController = TextEditingController();
  final _versionCountController = TextEditingController(text: '3');

  Quiz? _quiz;
  bool _creating = false;
  bool _uploading = false;
  bool _generating = false;
  int? _questionsInserted;
  List<RowError>? _uploadErrors;
  int? _versionsCreated;
  String? _error;

  Future<void> _createQuiz() async {
    if (_titleController.text.trim().isEmpty) return;
    setState(() {
      _creating = true;
      _error = null;
    });
    try {
      final quiz = await ref.read(quizzesProvider.notifier).create(_titleController.text.trim());
      setState(() => _quiz = quiz);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _creating = false);
    }
  }

  Future<void> _uploadExcel() async {
    final picked = await widget.pickFile();
    if (picked == null) return;

    setState(() {
      _uploading = true;
      _uploadErrors = null;
      _questionsInserted = null;
      _error = null;
    });
    try {
      final inserted =
          await ref.read(apiClientProvider).uploadExcel(_quiz!.id, picked.bytes, picked.filename);
      setState(() => _questionsInserted = inserted);
    } on ExcelValidationException catch (e) {
      setState(() => _uploadErrors = e.errors);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  Future<void> _generateVersions() async {
    final count = int.tryParse(_versionCountController.text);
    if (count == null || count < 1) {
      setState(() => _error = 'Enter a version count of at least 1');
      return;
    }
    setState(() {
      _generating = true;
      _error = null;
    });
    try {
      final created = await ref.read(apiClientProvider).generateVersions(_quiz!.id, count);
      setState(() => _versionsCreated = created);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _generating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 560),
        child: ListView(
          children: [
            Text('Create quiz', style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 24),
            if (_quiz == null) ...[
              TextField(
                key: const Key('quiz_title_field'),
                controller: _titleController,
                decoration: const InputDecoration(labelText: 'Quiz title'),
              ),
              const SizedBox(height: 16),
              ElevatedButton(
                key: const Key('create_quiz_button'),
                onPressed: _creating ? null : _createQuiz,
                child: _creating ? const _Spinner() : const Text('Create quiz'),
              ),
            ] else ...[
              Text('Quiz "${_quiz!.title}" created.'),
              const SizedBox(height: 16),
              if (_questionsInserted == null) ...[
                ElevatedButton(
                  key: const Key('upload_excel_button'),
                  onPressed: _uploading ? null : _uploadExcel,
                  child: _uploading ? const _Spinner() : const Text('Upload Excel'),
                ),
                if (_uploadErrors != null) ...[
                  const SizedBox(height: 16),
                  Text(
                    'The uploaded file has ${_uploadErrors!.length} invalid row(s):',
                    style: TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                  for (final rowError in _uploadErrors!)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        'Row ${rowError.rowNumber}: ${rowError.messages.join('; ')}',
                        key: Key('row_error_${rowError.rowNumber}'),
                      ),
                    ),
                ],
              ] else ...[
                Text('$_questionsInserted question(s) uploaded.'),
                const SizedBox(height: 16),
                if (_versionsCreated == null) ...[
                  TextField(
                    key: const Key('version_count_field'),
                    controller: _versionCountController,
                    decoration: const InputDecoration(labelText: 'Number of versions'),
                    keyboardType: TextInputType.number,
                  ),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    key: const Key('generate_versions_button'),
                    onPressed: _generating ? null : _generateVersions,
                    child: _generating ? const _Spinner() : const Text('Generate versions'),
                  ),
                ] else ...[
                  Text('$_versionsCreated version(s) generated.'),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    key: const Key('view_versions_button'),
                    onPressed: () =>
                        context.go('/quizzes/${_quiz!.id}/versions?title=${_quiz!.title}'),
                    child: const Text('View versions'),
                  ),
                ],
              ],
            ],
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 16),
                child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              ),
          ],
        ),
      ),
    );
  }
}

class _Spinner extends StatelessWidget {
  const _Spinner();
  @override
  Widget build(BuildContext context) =>
      const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2));
}
