import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../providers/queue_providers.dart';
import '../../services/image_quality.dart';

/// Full-screen camera capture with an inline retake prompt (Subtask 8.2).
/// The retake decision itself lives in [ImageQualityChecker] - a pure
/// function this screen calls on the captured bytes - so it's covered by
/// direct unit tests (test/services/image_quality_test.dart) against fixture
/// images rather than needing real camera hardware, which this dev
/// environment doesn't have (see PROGRESS.md Phase 0 notes).
class CameraCaptureScreen extends ConsumerStatefulWidget {
  const CameraCaptureScreen({super.key});

  @override
  ConsumerState<CameraCaptureScreen> createState() => _CameraCaptureScreenState();
}

class _CameraCaptureScreenState extends ConsumerState<CameraCaptureScreen> {
  static const _qualityChecker = ImageQualityChecker();

  CameraController? _controller;
  String? _initError;
  bool _capturing = false;
  String? _retakeReason;

  @override
  void initState() {
    super.initState();
    _initCamera();
  }

  Future<void> _initCamera() async {
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) {
        if (mounted) setState(() => _initError = 'No camera available on this device.');
        return;
      }
      final controller = CameraController(cameras.first, ResolutionPreset.high, enableAudio: false);
      await controller.initialize();
      if (!mounted) {
        await controller.dispose();
        return;
      }
      setState(() => _controller = controller);
    } catch (e) {
      if (mounted) setState(() => _initError = 'Camera unavailable: $e');
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  Future<void> _capture() async {
    final controller = _controller;
    if (controller == null || _capturing) return;
    setState(() {
      _capturing = true;
      _retakeReason = null;
    });
    try {
      final file = await controller.takePicture();
      final bytes = await File(file.path).readAsBytes();
      final quality = _qualityChecker.evaluate(bytes);
      if (quality.needsRetake) {
        if (mounted) {
          setState(() {
            _retakeReason = quality.isBlurry
                ? 'Image looks blurry - hold steady and retake.'
                : 'No page detected in frame - retake.';
          });
        }
        return;
      }
      await ref.read(queueControllerProvider.notifier).addCapture(bytes);
    } finally {
      if (mounted) setState(() => _capturing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final queueLength = ref.watch(queueControllerProvider).length;
    return Scaffold(
      appBar: AppBar(
        title: Text('Scan ($queueLength captured)'),
        actions: [
          IconButton(
            key: const Key('go_to_summary_button'),
            icon: const Icon(Icons.check_circle_outline),
            onPressed: () => context.go('/summary'),
          ),
        ],
      ),
      body: Stack(
        children: [
          if (_controller != null && _controller!.value.isInitialized)
            Positioned.fill(child: CameraPreview(_controller!))
          else
            Center(child: Text(_initError ?? 'Initializing camera...')),
          if (_retakeReason != null)
            Positioned(
              left: 16,
              right: 16,
              bottom: 96,
              child: Material(
                color: Theme.of(context).colorScheme.errorContainer,
                borderRadius: BorderRadius.circular(8),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text(
                    _retakeReason!,
                    key: const Key('retake_prompt'),
                    style: TextStyle(color: Theme.of(context).colorScheme.onErrorContainer),
                  ),
                ),
              ),
            ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 24,
            child: Center(
              child: FloatingActionButton.large(
                key: const Key('capture_button'),
                onPressed: _controller == null || _capturing ? null : _capture,
                child: _capturing
                    ? const CircularProgressIndicator()
                    : const Icon(Icons.camera_alt),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
