/** TypeScript port of mobile/lib/services/image_quality.dart's
 * `ImageQualityChecker` (Phase 8.2), reused for the web capture screen's
 * retake prompt (Subtask 7c.2). Same algorithm and same thresholds - a fast,
 * deterministic, local pre-check only ("is this worth uploading at all"),
 * not the real OMR pipeline, which stays server-side (Phase 5/6). No LLM
 * calls anywhere, per CLAUDE.md Section 2 Rule 1. */

export interface CaptureQuality {
  isBlurry: boolean;
  qrLikelyVisible: boolean;
  sharpnessScore: number;
  needsRetake: boolean;
}

/** Minimal shape shared with canvas `ImageData` - a captured video frame is
 * always drawn to an offscreen canvas and read back via
 * `getImageData().data`, so this accepts that directly without depending on
 * the DOM `ImageData` type (keeps the pure function unit-testable in Vitest
 * without a real canvas/jsdom `ImageData` polyfill). */
export interface RgbaFrame {
  width: number;
  height: number;
  data: Uint8ClampedArray | Uint8Array;
}

/** Variance-of-Laplacian threshold below which a page is judged blurry.
 *
 * Originally 500.0, ported unchanged from the Dart original's
 * `blurThreshold` - but that value was itself only ever calibrated against
 * a synthetic maximal-edge-density checkerboard test fixture, on *either*
 * client, never against a real camera frame (no camera hardware existed in
 * this dev environment until web's browser-based capture, Phase 7c). A real
 * printed exam page is mostly white background with comparatively sparse
 * black text/bubbles - nothing like a checkerboard - so this consistently
 * under-measured real captures as "blurry" even when visually sharp,
 * confirmed live 2026-08-24: a real capture judged visually fine by the
 * professor testing it scored sharpnessScore=361 against the old
 * threshold=500. Lowered to comfortably clear that real data point while
 * staying well above the near-zero variance of a genuinely blank/flat
 * frame - not re-derived from further real samples (only the one data
 * point exists so far), so this may need another pass once more real
 * captures - including a genuinely blurry one - are available to bound the
 * other side of the range. Low risk if still imperfect: this is only a
 * fast local "worth uploading" pre-check, not the authoritative quality
 * gate - the backend's real per-bubble classifier confidence gate
 * (CLAUDE.md Section 2 Rule 5) still catches genuinely unscoreable
 * captures and routes them to review rather than silently scoring them
 * wrong. */
const BLUR_THRESHOLD = 150.0;

/** A blank/near-uniform frame has near-zero pixel-intensity spread; a
 * printed answer sheet with a QR code does not. Identical value to the Dart
 * original's `minIntensityStdDev`. Actual QR decoding happens server-side
 * (backend/app/routers/scan.py via pyzbar) - this is only a coarse
 * "something is in frame" stand-in. */
const MIN_INTENSITY_STD_DEV = 15.0;

function toGrayscale(frame: RgbaFrame): Float64Array {
  const { width, height, data } = frame;
  const gray = new Float64Array(width * height);
  for (let i = 0, p = 0; p < gray.length; i += 4, p++) {
    // ITU-R BT.601 luma. Equivalent to the Dart `image` package's grayscale
    // conversion for true black/white pixels (the synthetic test fixtures
    // this threshold was tuned against), which is the only case that
    // matters for this coarse pre-check.
    gray[p] = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
  }
  return gray;
}

function intensityStdDev(gray: Float64Array): number {
  if (gray.length === 0) return 0;
  let sum = 0;
  for (const v of gray) sum += v;
  const mean = sum / gray.length;
  let sqSum = 0;
  for (const v of gray) sqSum += (v - mean) * (v - mean);
  return Math.sqrt(sqSum / gray.length);
}

/** Variance of the 3x3 Laplacian response across the image - same fast blur
 * metric as the Dart original (low variance = few sharp edges = likely out
 * of focus). */
function laplacianVariance(gray: Float64Array, width: number, height: number): number {
  if (width < 3 || height < 3) return 0;

  const count = (width - 2) * (height - 2);
  const responses = new Float64Array(count);
  let idx = 0;
  for (let y = 1; y < height - 1; y++) {
    for (let x = 1; x < width - 1; x++) {
      const center = gray[y * width + x];
      const up = gray[(y - 1) * width + x];
      const down = gray[(y + 1) * width + x];
      const left = gray[y * width + x - 1];
      const right = gray[y * width + x + 1];
      responses[idx] = up + down + left + right - 4 * center;
      idx++;
    }
  }

  let sum = 0;
  for (const r of responses) sum += r;
  const mean = sum / responses.length;

  let sqSum = 0;
  for (const r of responses) sqSum += (r - mean) * (r - mean);
  return sqSum / responses.length;
}

export function evaluateCaptureQuality(
  frame: RgbaFrame,
  options: { blurThreshold?: number; minIntensityStdDev?: number } = {},
): CaptureQuality {
  const blurThreshold = options.blurThreshold ?? BLUR_THRESHOLD;
  const minIntensityStdDev = options.minIntensityStdDev ?? MIN_INTENSITY_STD_DEV;

  if (frame.width === 0 || frame.height === 0 || frame.data.length === 0) {
    return { isBlurry: true, qrLikelyVisible: false, sharpnessScore: 0, needsRetake: true };
  }

  const gray = toGrayscale(frame);
  const variance = laplacianVariance(gray, frame.width, frame.height);
  const stdDev = intensityStdDev(gray);
  const isBlurry = variance < blurThreshold;
  const qrLikelyVisible = stdDev >= minIntensityStdDev;
  return {
    isBlurry,
    qrLikelyVisible,
    sharpnessScore: variance,
    needsRetake: isBlurry || !qrLikelyVisible,
  };
}
