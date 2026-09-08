import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { useScanQueue } from "@/lib/scan/useScanQueue";
import type { ScanApi, ScanResult } from "@/lib/scan/scanApi";

const fakeResult: ScanResult = {
  submissionId: "sub-1",
  status: "finalized",
  totalScore: 3,
  studentName: "Jane Doe",
  nameFlagged: false,
  flaggedQuestionNumbers: [],
};

function fakeBlob(): Blob {
  return new Blob(["fake-jpeg-bytes"], { type: "image/jpeg" });
}

/** Mirrors mobile/test's fake-`ScanApi` pattern for
 * mobile/lib/services/sync_service.dart: retry/failure-state logic is
 * unit-tested against an injected fake, not a real network or camera
 * (Subtask 7c.3 DoD). */
class FakeScanApi implements ScanApi {
  calls = 0;
  receivedCaptureIds: string[] = [];
  constructor(private readonly behavior: (call: number) => Promise<ScanResult>) {}

  submitScan(_blob: Blob, _accessToken: string | null, captureId: string): Promise<ScanResult> {
    this.calls++;
    this.receivedCaptureIds.push(captureId);
    return this.behavior(this.calls);
  }
}

describe("useScanQueue", () => {
  test("a successful submission ends in the submitted state with the parsed result", async () => {
    const api = new FakeScanApi(async () => fakeResult);
    const { result } = renderHook(() => useScanQueue(api, async () => "token"));

    act(() => {
      result.current.submit(fakeBlob());
    });

    await waitFor(() => expect(result.current.sheets[0].state).toBe("submitted"));
    expect(result.current.sheets).toHaveLength(1);
    expect(result.current.sheets[0].result).toEqual(fakeResult);
  });

  test("a network failure marks the sheet failed/not-submitted and never counts it as submitted", async () => {
    const api = new FakeScanApi(async () => {
      throw new TypeError("Failed to fetch");
    });
    const { result } = renderHook(() => useScanQueue(api, async () => "token"));

    act(() => {
      result.current.submit(fakeBlob());
    });

    await waitFor(() => expect(result.current.sheets[0].state).toBe("failed"));
    expect(result.current.sheets).toHaveLength(1);
    expect(result.current.sheets[0].result).toBeUndefined();
    expect(result.current.sheets.some((s) => s.state === "submitted")).toBe(false);
  });

  test("an expired session (getAccessToken throws) fails the sheet without ever calling submitScan", async () => {
    // web-app audit A2: the web /scan screen is behind auth and must never
    // submit a scan anonymously. If the session has expired, the throw from
    // getAccessToken must land the sheet in "failed / not submitted", not
    // reach the still-open backend route with no token.
    const api = new FakeScanApi(async () => fakeResult);
    const { result } = renderHook(() =>
      useScanQueue(api, async () => {
        throw new Error("no active session");
      }),
    );

    act(() => {
      result.current.submit(fakeBlob());
    });

    await waitFor(() => expect(result.current.sheets[0].state).toBe("failed"));
    expect(api.calls).toBe(0);
    expect(result.current.sheets[0].result).toBeUndefined();
    expect(result.current.sheets.some((s) => s.state === "submitted")).toBe(false);
  });

  test("retrying a failed sheet resubmits the same captured blob and can succeed", async () => {
    const api = new FakeScanApi(async (call) => {
      if (call === 1) throw new TypeError("Failed to fetch");
      return fakeResult;
    });
    const { result } = renderHook(() => useScanQueue(api, async () => "token"));

    act(() => {
      result.current.submit(fakeBlob());
    });
    await waitFor(() => expect(result.current.sheets[0].state).toBe("failed"));

    const id = result.current.sheets[0].id;
    act(() => {
      result.current.retry(id);
    });

    await waitFor(() => expect(result.current.sheets[0].state).toBe("submitted"));
    expect(api.calls).toBe(2);
    expect(result.current.sheets[0].result).toEqual(fakeResult);
  });

  test("retrying a failed sheet sends the same capture_id as the original attempt", async () => {
    // The backend dedupes on capture_id (0005_scan_capture_id migration) -
    // a retry must reuse the id from the original attempt, not generate a
    // fresh one, or a request that actually succeeded server-side despite a
    // lost response would create a duplicate submission on retry.
    const api = new FakeScanApi(async (call) => {
      if (call === 1) throw new TypeError("Failed to fetch");
      return fakeResult;
    });
    const { result } = renderHook(() => useScanQueue(api, async () => "token"));

    act(() => {
      result.current.submit(fakeBlob());
    });
    await waitFor(() => expect(result.current.sheets[0].state).toBe("failed"));

    const id = result.current.sheets[0].id;
    act(() => {
      result.current.retry(id);
    });
    await waitFor(() => expect(result.current.sheets[0].state).toBe("submitted"));

    expect(api.receivedCaptureIds).toHaveLength(2);
    expect(api.receivedCaptureIds[0]).toBe(api.receivedCaptureIds[1]);
    expect(api.receivedCaptureIds[0]).toBeTruthy();
  });
});
