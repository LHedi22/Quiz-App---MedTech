/** Client for `POST /scan` (backend/app/routers/scan.py), used only by the
 * web capture screen (Subtask 7c.3). Mirrors mobile/lib/services/
 * api_client.dart's `ApiClient.scanSubmission` - same endpoint, same
 * multipart shape.
 *
 * The route has no `Depends(get_current_user)` server-side - a deliberate
 * carry-over for the Flutter offline path, which has no session at scan
 * time. The web app does NOT rely on that: its /scan screen is behind the
 * authenticated `(app)` route group and always passes a real token (see
 * `requireAccessToken` in app/(app)/scan/page.tsx). `accessToken` is typed
 * nullable only so the mobile-shaped fake in the tests can omit it; the web
 * wiring never passes null. See web-app audit A2 / docs/BLOCKERS.md for the
 * open decision on requiring auth on this route outright. */

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
