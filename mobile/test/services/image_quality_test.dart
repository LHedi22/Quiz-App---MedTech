import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;

import 'package:exam_scanner_mobile/services/image_quality.dart';

/// Subtask 8.2's DoD requires testing the retake-prompt decision with "a
/// deliberately blurred fixture image fed through the same detection logic"
/// the camera screen uses. These fixtures are generated in-test (a
/// checkerboard page with a QR-style finder pattern, then a heavily
/// Gaussian-blurred copy of the same page) rather than checked-in binary
/// files, so the test is fully deterministic and self-contained.
Uint8List _sharpTestPage() {
  final image = img.Image(width: 240, height: 240);
  img.fill(image, color: img.ColorRgb8(255, 255, 255));

  const cell = 12;
  for (var y = 0; y < image.height; y += cell) {
    for (var x = 0; x < image.width; x += cell) {
      final isDark = ((x ~/ cell) + (y ~/ cell)).isEven;
      if (isDark) {
        img.fillRect(image,
            x1: x, y1: y, x2: x + cell - 1, y2: y + cell - 1, color: img.ColorRgb8(0, 0, 0));
      }
    }
  }

  // Nested squares mimicking a QR finder pattern, in one corner - like the
  // real printed template's QR code.
  img.fillRect(image, x1: 8, y1: 8, x2: 40, y2: 40, color: img.ColorRgb8(0, 0, 0));
  img.fillRect(image, x1: 14, y1: 14, x2: 34, y2: 34, color: img.ColorRgb8(255, 255, 255));
  img.fillRect(image, x1: 20, y1: 20, x2: 28, y2: 28, color: img.ColorRgb8(0, 0, 0));

  return Uint8List.fromList(img.encodePng(image));
}

Uint8List _blurredTestPage() {
  final image = img.decodeImage(_sharpTestPage())!;
  final blurred = img.gaussianBlur(image, radius: 15);
  return Uint8List.fromList(img.encodePng(blurred));
}

Uint8List _blankPage() {
  final image = img.Image(width: 240, height: 240);
  img.fill(image, color: img.ColorRgb8(255, 255, 255));
  return Uint8List.fromList(img.encodePng(image));
}

void main() {
  const checker = ImageQualityChecker();

  test('a sharp fixture image proceeds without a false-positive retake prompt', () {
    final quality = checker.evaluate(_sharpTestPage());
    expect(quality.isBlurry, isFalse);
    expect(quality.qrLikelyVisible, isTrue);
    expect(quality.needsRetake, isFalse);
  });

  test('a deliberately blurred fixture image triggers the retake prompt', () {
    final sharp = checker.evaluate(_sharpTestPage());
    final blurry = checker.evaluate(_blurredTestPage());

    // The blur must actually have reduced measured sharpness, not just
    // happen to land under the threshold by coincidence.
    expect(blurry.sharpnessScore, lessThan(sharp.sharpnessScore));
    expect(blurry.isBlurry, isTrue);
    expect(blurry.needsRetake, isTrue);
  });

  test('a blank/empty frame is flagged as needing retake (no QR visible)', () {
    final quality = checker.evaluate(_blankPage());
    expect(quality.qrLikelyVisible, isFalse);
    expect(quality.needsRetake, isTrue);
  });

  test('unreadable bytes are treated as needing retake rather than crashing', () {
    final quality = checker.evaluate(Uint8List.fromList([1, 2, 3, 4]));
    expect(quality.needsRetake, isTrue);
  });
}
