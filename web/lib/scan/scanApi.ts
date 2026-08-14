/** Client for `POST /scan` (backend/app/routers/scan.py), used only by the
 * web capture screen (Subtask 7c.3). Mirrors mobile/lib/services/
 * api_client.dart's `ApiClient.scanSubmission` - same endpoint, same
 * multipart shape, same optional Bearer token (the route itself has no
 * `Depends(get_current_user)`, so a missing token is not an error here,
 * unlike every other route this app calls). */

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
  submitScan(blob: Blob, accessToken: string | null): Promise<ScanResult>;
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

  async submitScan(blob: Blob, accessToken: string | null): Promise<ScanResult> {
    const formData = new FormData();
    formData.append("file", blob, "scan.jpg");

    const response = await fetch(`${this.baseUrl}/scan`, {
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
