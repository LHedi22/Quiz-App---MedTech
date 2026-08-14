import { describe, expect, test } from "vitest";
import { evaluateCaptureQuality, type RgbaFrame } from "@/lib/scan/imageQuality";

/** Mirrors mobile/test/services/image_quality_test.dart's fixtures: a
 * checkerboard page with a QR-finder-style corner pattern in true
 * black/white (so luma weighting is irrelevant), then a heavily blurred
 * copy of the same page - generated in-test, not checked-in binary files,
 * so this stays fully deterministic (Subtask 7c.2 DoD). */
function sharpTestFrame(): RgbaFrame {
  const size = 240;
  const cell = 12;
  const data = new Uint8ClampedArray(size * size * 4);

  const setPixel = (x: number, y: number, value: number) => {
    const i = (y * size + x) * 4;
    data[i] = value;
    data[i + 1] = value;
    data[i + 2] = value;
    data[i + 3] = 255;
  };

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const isDark = (Math.floor(x / cell) + Math.floor(y / cell)) % 2 === 0;
      setPixel(x, y, isDark ? 0 : 255);
    }
  }

  // Nested squares mimicking a QR finder pattern in one corner, like the
  // real printed template's QR code.
  const fillRect = (x1: number, y1: number, x2: number, y2: number, value: number) => {
    for (let y = y1; y <= y2; y++) {
      for (let x = x1; x <= x2; x++) setPixel(x, y, value);
    }
  };
  fillRect(8, 8, 40, 40, 0);
  fillRect(14, 14, 34, 34, 255);
  fillRect(20, 20, 28, 28, 0);

  return { width: size, height: size, data };
}

/** A repeated box blur - not the Dart fixture's Gaussian, but the same
 * role (test infrastructure that heavily smooths the fixture, not the
 * ported algorithm itself, whose thresholds are untouched). */
function boxBlur(frame: RgbaFrame, radius: number, passes: number): RgbaFrame {
  let { data } = frame;
  const { width, height } = frame;

  for (let pass = 0; pass < passes; pass++) {
    const out = new Uint8ClampedArray(data.length);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        let sum = 0;
        let n = 0;
        for (let dy = -radius; dy <= radius; dy++) {
          for (let dx = -radius; dx <= radius; dx++) {
            const nx = x + dx;
            const ny = y + dy;
            if (nx < 0 || nx >= width || ny < 0 || ny >= height) continue;
            sum += data[(ny * width + nx) * 4];
            n++;
          }
        }
        const value = Math.round(sum / n);
        const i = (y * width + x) * 4;
        out[i] = value;
        out[i + 1] = value;
        out[i + 2] = value;
        out[i + 3] = 255;
      }
    }
    data = out;
  }

  return { width, height, data };
}

function blurredTestFrame(): RgbaFrame {
  return boxBlur(sharpTestFrame(), 8, 3);
}

function blankFrame(): RgbaFrame {
  const size = 240;
  const data = new Uint8ClampedArray(size * size * 4);
  for (let p = 0; p < data.length; p += 4) {
    data[p] = 255;
    data[p + 1] = 255;
    data[p + 2] = 255;
    data[p + 3] = 255;
  }
  return { width: size, height: size, data };
}

describe("evaluateCaptureQuality", () => {
  test("a sharp fixture image proceeds without a false-positive retake prompt", () => {
    const quality = evaluateCaptureQuality(sharpTestFrame());
    expect(quality.isBlurry).toBe(false);
    expect(quality.qrLikelyVisible).toBe(true);
    expect(quality.needsRetake).toBe(false);
  });

  test("a deliberately blurred fixture image triggers the retake prompt", () => {
    const sharp = evaluateCaptureQuality(sharpTestFrame());
    const blurry = evaluateCaptureQuality(blurredTestFrame());

    // The blur must actually have reduced measured sharpness, not just
    // happen to land under the threshold by coincidence.
    expect(blurry.sharpnessScore).toBeLessThan(sharp.sharpnessScore);
    expect(blurry.isBlurry).toBe(true);
    expect(blurry.needsRetake).toBe(true);
  });

  test("a blank/empty frame is flagged as needing retake (no QR visible)", () => {
    const quality = evaluateCaptureQuality(blankFrame());
    expect(quality.qrLikelyVisible).toBe(false);
    expect(quality.needsRetake).toBe(true);
  });

  test("a degenerate zero-size frame is treated as needing retake rather than crashing", () => {
    const quality = evaluateCaptureQuality({ width: 0, height: 0, data: new Uint8ClampedArray(0) });
    expect(quality.needsRetake).toBe(true);
  });
});
