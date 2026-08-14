import type { ScanSheet } from "./useScanQueue";

/** In-session batch summary (Subtask 7c.4) - derived purely from the
 * capture queue's own state, no separate source of truth to drift out of
 * sync with. `attempted` counts every sheet that has ever been submitted at
 * least once, including ones currently `submitting` or `failed`; a sheet
 * only ever contributes to exactly one of `finalized`/`needsReview`/`failed`. */
export interface BatchSummary {
  attempted: number;
  finalized: number;
  needsReview: number;
  failed: number;
}

export function summarizeSheets(sheets: ScanSheet[]): BatchSummary {
  let finalized = 0;
  let needsReview = 0;
  let failed = 0;

  for (const sheet of sheets) {
    if (sheet.state === "failed") {
      failed++;
    } else if (sheet.state === "submitted" && sheet.result) {
      if (sheet.result.status === "finalized") finalized++;
      else if (sheet.result.status === "needs_review") needsReview++;
    }
  }

  return { attempted: sheets.length, finalized, needsReview, failed };
}

/** Submission ids for this session's needs_review sheets, in capture order -
 * the exact set the "Review flagged" link must resolve to, and nothing else
 * (Subtask 7c.4 DoD). */
export function needsReviewSubmissionIds(sheets: ScanSheet[]): string[] {
  return sheets
    .filter((sheet) => sheet.state === "submitted" && sheet.result?.status === "needs_review")
    .map((sheet) => sheet.result!.submissionId);
}
