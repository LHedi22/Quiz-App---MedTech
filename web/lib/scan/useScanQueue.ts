"use client";

import { useCallback, useRef, useState } from "react";
import type { ScanApi, ScanResult } from "./scanApi";

export type SheetState = "submitting" | "submitted" | "failed";

export interface ScanSheet {
  id: string;
  state: SheetState;
  result?: ScanResult;
  errorMessage?: string;
}

/** Per-session capture queue for the web scan screen (Subtask 7c.3).
 * Deliberately has no persistence (no IndexedDB/localStorage) and no
 * background sync - a failed sheet stays failed until the professor taps
 * "Retry" themselves, per this phase's locked "no offline queue" decision
 * in prompts/07c_web_responsive_scanning.md. Mirrors
 * mobile/lib/services/sync_service.dart's shape (an injected [ScanApi] so
 * retry logic is unit-testable against a fake, not a real network/camera -
 * same reasoning as that file's own docstring, and this dev environment
 * has no usable fake-camera-device setup either).
 *
 * `getAccessToken` is called inside the submit attempt: if it throws (the
 * web wiring passes a variant that throws on an expired session rather than
 * submitting anonymously - web-app audit A2), the sheet lands in the same
 * "failed / not submitted - retry" state as a network drop or a backend
 * rejection, never silently counted as processed. */
export function useScanQueue(api: ScanApi, getAccessToken: () => Promise<string | null>) {
  const [sheets, setSheets] = useState<ScanSheet[]>([]);
  const blobsRef = useRef<Map<string, Blob>>(new Map());
  // One id generated per captured sheet, reused on every attempt for that
  // sheet - including retry() - so a retry after a lost response (the
  // original request actually succeeded server-side, the client just never
  // saw it) returns the existing submission instead of creating a
  // duplicate. See backend/migrations/0005_scan_capture_id.up.sql.
  const captureIdsRef = useRef<Map<string, string>>(new Map());
  const nextIdRef = useRef(0);

  const attempt = useCallback(
    async (id: string, blob: Blob) => {
      setSheets((prev) =>
        prev.map((s) => (s.id === id ? { ...s, state: "submitting", errorMessage: undefined } : s)),
      );
      try {
        const token = await getAccessToken();
        const captureId = captureIdsRef.current.get(id)!;
        const result = await api.submitScan(blob, token, captureId);
        setSheets((prev) => (prev.map((s) => (s.id === id ? { ...s, state: "submitted", result } : s))));
      } catch (err) {
        // Network drop mid-flight and a definite backend rejection (e.g.
        // qr_unreadable) land here the same way: neither creates a
        // submission server-side, so both are "not submitted - retry", not
        // silently counted as processed (Subtask 7c.3 DoD).
        setSheets((prev) =>
          prev.map((s) =>
            s.id === id
              ? {
                  ...s,
                  state: "failed",
                  errorMessage: err instanceof Error ? err.message : String(err),
                }
              : s,
          ),
        );
      }
    },
    [api, getAccessToken],
  );

  const submit = useCallback(
    (blob: Blob) => {
      const id = `sheet-${nextIdRef.current++}`;
      blobsRef.current.set(id, blob);
      captureIdsRef.current.set(id, crypto.randomUUID());
      setSheets((prev) => [...prev, { id, state: "submitting" }]);
      void attempt(id, blob);
      return id;
    },
    [attempt],
  );

  const retry = useCallback(
    (id: string) => {
      const blob = blobsRef.current.get(id);
      if (!blob) return;
      void attempt(id, blob);
    },
    [attempt],
  );

  return { sheets, submit, retry };
}
