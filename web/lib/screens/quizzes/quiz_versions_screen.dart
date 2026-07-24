import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/api_providers.dart';
import '../../providers/quiz_providers.dart';
import '../../services/download/download.dart' as download;

typedef DownloadBytesFn = void Function(Uint8List bytes, String filename);

/// Subtask 7.3: list generated versions with a download button per version.
class QuizVersionsScreen extends ConsumerStatefulWidget {
  final String quizId;
  final String quizTitle;
  final DownloadBytesFn downloadBytes;

  QuizVersionsScreen({
    super.key,
    required this.quizId,
    required this.quizTitle,
    DownloadBytesFn? downloadBytes,
  }) : downloadBytes = downloadBytes ?? download.downloadBytes;

  @override
  ConsumerState<QuizVersionsScreen> createState() => _QuizVersionsScreenState();
}

class _QuizVersionsScreenState extends ConsumerState<QuizVersionsScreen> {
  final Set<String> _downloading = {};
  String? _error;

  Future<void> _download(String versionId, int versionNumber) async {
    setState(() {
      _downloading.add(versionId);
      _error = null;
    });
    try {
      final bytes = await ref.read(apiClientProvider).downloadVersionPdf(versionId);
      widget.downloadBytes(bytes, '${widget.quizTitle}_v$versionNumber.pdf');
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _downloading.remove(versionId));
    }
  }

  @override
  Widget build(BuildContext context) {
    final versionsAsync = ref.watch(quizVersionsProvider(widget.quizId));
    return Scaffold(
      appBar: AppBar(title: Text('${widget.quizTitle} - Versions')),
      body: Column(
        children: [
          if (_error != null)
            Padding(
              padding: const EdgeInsets.all(12),
              child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          Expanded(
            child: versionsAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (err, st) => Center(child: Text('Failed to load versions: $err')),
              data: (versions) {
                if (versions.isEmpty) {
                  return const Center(child: Text('No versions generated yet.'));
                }
                return ListView.builder(
                  itemCount: versions.length,
                  itemBuilder: (context, index) {
                    final version = versions[index];
                    final isDownloading = _downloading.contains(version.id);
                    return ListTile(
                      key: Key('version_tile_${version.id}'),
                      title: Text('Version ${version.versionNumber}'),
                      trailing: IconButton(
                        key: Key('download_button_${version.id}'),
                        icon: isDownloading
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.download),
                        onPressed:
                            isDownloading ? null : () => _download(version.id, version.versionNumber),
                      ),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
