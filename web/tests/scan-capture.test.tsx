import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const submit = vi.fn();

vi.mock("@/lib/scan/useScanQueue", () => ({
  useScanQueue: () => ({ sheets: [], submit, retry: vi.fn() }),
}));
vi.mock("@/lib/scan/useReachability", () => ({
  useReachability: () => true,
}));
vi.mock("@/lib/scan/scanApi", () => ({
  RealScanApi: class {},
}));
vi.mock("@/lib/scan/imageQuality", () => ({
  evaluateCaptureQuality: () => ({ needsRetake: false, isBlurry: false }),
}));
vi.mock("@/lib/scan/summary", () => ({
  summarizeSheets: () => ({ attempted: 0, finalized: 0, needsReview: 0, failed: 0 }),
  needsReviewSubmissionIds: () => [],
}));
vi.mock("@/lib/supabase/client", () => ({
  getAccessToken: () => Promise.resolve("token"),
}));

import ScanPage from "@/app/(app)/scan/page";

let toBlobCallbacks: Array<() => void> = [];

beforeEach(() => {
  vi.clearAllMocks();
  toBlobCallbacks = [];

  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }),
    },
  });
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true });

  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(HTMLVideoElement.prototype, "videoWidth", {
    configurable: true,
    get: () => 1920,
  });
  Object.defineProperty(HTMLVideoElement.prototype, "videoHeight", {
    configurable: true,
    get: () => 1080,
  });

  HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
    drawImage: vi.fn(),
    getImageData: vi.fn().mockReturnValue({ data: new Uint8ClampedArray(4), width: 1, height: 1 }),
  }) as unknown as typeof HTMLCanvasElement.prototype.getContext;

  // Async, like the real toBlob: the callback only runs when we flush it.
  HTMLCanvasElement.prototype.toBlob = vi.fn((cb: BlobCallback) => {
    toBlobCallbacks.push(() => cb(new Blob(["x"], { type: "image/jpeg" })));
  });
});

afterEach(() => {
  cleanup();
});

describe("scan capture — double tap", () => {
  it("a fast second tap before the frame finishes encoding does not create a second submission", async () => {
    render(<ScanPage />);

    const button = await screen.findByTestId("capture-button");
    await waitFor(() => expect(button).not.toBeDisabled());

    // Two taps in the window between toBlob being called and its callback
    // firing.
    fireEvent.click(button);
    fireEvent.click(button);

    expect(HTMLCanvasElement.prototype.toBlob).toHaveBeenCalledTimes(1);

    // Flush the pending encode.
    toBlobCallbacks.forEach((run) => run());
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
  });

  it("after a completed capture the button works again for the next sheet", async () => {
    render(<ScanPage />);
    const button = await screen.findByTestId("capture-button");
    await waitFor(() => expect(button).not.toBeDisabled());

    fireEvent.click(button);
    toBlobCallbacks.shift()!();
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));

    await waitFor(() => expect(button).not.toBeDisabled());
    fireEvent.click(button);
    toBlobCallbacks.shift()!();
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(2));
  });
});
