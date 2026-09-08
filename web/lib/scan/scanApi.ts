/** Client for `POST /scan` (backend/app/routers/scan.py), used only by the
 * web capture screen (Subtask 7c.3).
 *
 * `POST /scan` requires a Supabase bearer token and scopes the scan to the
 * professor who owns the scanned version's quiz (web-app audit A2 - the app
 * is web-only now, see docs/BLOCKERS.md). The web `/scan` screen is behind
 * the authenticated `(app)` route group, so a token is always available
 * (`requireAccessToken` in app/(app)/scan/page.tsx). `accessToken` is typed
 * nullable only so the mobile-shaped fake in the tests can omit it; the web
 * wiring never passes null. */

export interface ScanResult {
  submissionId: string;
  status: "pending" | "needs_review" | "finalized";
  totalScore: number | null;
  studentName: string | null;
  nameFlagged: boolean;
  flaggedQuestionNumbers: number[];
}

export class ScanSubmitError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`scan submission failed with status ${status}`);
  }
}

export interface ScanApi {
  submitScan(blob: Blob, accessToken: string | null, captureId: string): Promise<ScanResult>;
}

function parseScanResult(data: Record<string, unknown>): ScanResult {
  return {
    submissionId: String(data.submission_id),
    status: data.status as ScanResult["status"],
    totalScore: typeof data.total_score === "number" ? data.total_score : null,
    studentName: typeof data.student_name === "string" ? data.student_name : null,
    nameFlagged: Boolean(data.name_flagged),
    flaggedQuestionNumbers: Array.isArray(data.flagged_question_numbers)
      ? (data.flagged_question_numbers as number[])
      : [],
  };
}

export class RealScanApi implements ScanApi {
  constructor(private readonly baseUrl: string) {}

  async submitScan(blob: Blob, accessToken: string | null, captureId: string): Promise<ScanResult> {
    const formData = new FormData();
    formData.append("file", blob, "scan.jpg");

    const url = new URL(`${this.baseUrl}/scan`);
    url.searchParams.set("capture_id", captureId);

    const response = await fetch(url, {
      method: "POST",
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
      body: formData,
    });

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new ScanSubmitError(response.status, body);
    }

    return parseScanResult(await response.json());
  }
}
