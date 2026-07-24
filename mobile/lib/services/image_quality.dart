import 'dart:math';
import 'dart:typed_data';

import 'package:image/image.dart' as img;

/// Result of a fast local pre-check on a just-captured page (Subtask 8.2).
/// This is deliberately *not* the full ML/OMR pipeline (Phase 5/6, which
/// runs server-side) - it only answers "is this worth uploading at all", so
/// a professor can retake a bad shot before moving to the next sheet.
class CaptureQuality {
  final bool isBlurry;
  final bool qrLikelyVisible;
  final double sharpnessScore;

  CaptureQuality({
    required this.isBlurry,
    required this.qrLikelyVisible,
    required this.sharpnessScore,
  });

  bool get needsRetake => isBlurry || !qrLikelyVisible;
}

/// Pure, deterministic image analysis (no LLM, no network - see CLAUDE.md
/// Section 2) backing the capture screen's retake prompt.
class ImageQualityChecker {
  /// Variance-of-Laplacian threshold below which a page is judged blurry.
  /// Chosen empirically (see test/services/image_quality_test.dart): a
  /// sharp synthetic test page scores in the several-thousands; the same
  /// page through a strong Gaussian blur drops below 100.
  final double blurThreshold;

  /// A blank/near-uniform frame (nothing in view, lens cap, pointed at a
  /// wall) has near-zero pixel-intensity spread; a printed answer sheet
  /// with a QR code does not. This is a coarse stand-in for "is there a QR
  /// code in frame" - actual decoding happens server-side via pyzbar (see
  /// backend/app/routers/scan.py), which also handles the case where this
  /// check passes but the QR itself still isn't decodable.
  final double minIntensityStdDev;

  const ImageQualityChecker({this.blurThreshold = 500.0, this.minIntensityStdDev = 15.0});

  CaptureQuality evaluate(Uint8List imageBytes) {
    img.Image? decoded;
    try {
      decoded = img.decodeImage(imageBytes);
    } catch (_) {
      // Malformed/truncated bytes can make the decoder's format sniffing
      // throw instead of returning null (observed with very short garbage
      // input) - either way, an undecodable capture needs a retake.
      decoded = null;
    }
    if (decoded == null) {
      return CaptureQuality(isBlurry: true, qrLikelyVisible: false, sharpnessScore: 0);
    }
    final gray = img.grayscale(decoded);
    final variance = _laplacianVariance(gray);
    final stdDev = _intensityStdDev(gray);
    return CaptureQuality(
      isBlurry: variance < blurThreshold,
      qrLikelyVisible: stdDev >= minIntensityStdDev,
      sharpnessScore: variance,
    );
  }

  double _intensityStdDev(img.Image gray) {
    final values = <double>[];
    for (final pixel in gray) {
      values.add(pixel.r.toDouble());
    }
    if (values.isEmpty) return 0;
    final mean = values.reduce((a, b) => a + b) / values.length;
    final variance = values.map((v) => (v - mean) * (v - mean)).reduce((a, b) => a + b) / values.length;
    return sqrt(variance);
  }

  /// Variance of the 3x3 Laplacian response across the image - a standard,
  /// fast blur metric (low variance = few sharp edges = likely out of
  /// focus).
  double _laplacianVariance(img.Image gray) {
    final width = gray.width;
    final height = gray.height;
    if (width < 3 || height < 3) return 0;

    final responses = Float64List((width - 2) * (height - 2));
    var idx = 0;
    for (var y = 1; y < height - 1; y++) {
      for (var x = 1; x < width - 1; x++) {
        final center = gray.getPixel(x, y).r;
        final up = gray.getPixel(x, y - 1).r;
        final down = gray.getPixel(x, y + 1).r;
        final left = gray.getPixel(x - 1, y).r;
        final right = gray.getPixel(x + 1, y).r;
        responses[idx] = (up + down + left + right - 4 * center).toDouble();
        idx++;
      }
    }

    var sum = 0.0;
    for (final r in responses) {
      sum += r;
    }
    final mean = sum / responses.length;

    var sqSum = 0.0;
    for (final r in responses) {
      final diff = r - mean;
      sqSum += diff * diff;
    }
    return sqSum / responses.length;
  }
}
