import { describe, expect, test } from "vitest";
import { needsReviewSubmissionIds, summarizeSheets } from "@/lib/scan/summary";
import type { ScanSheet } from "@/lib/scan/useScanQueue";

function sheet(overrides: Partial<ScanSheet>): ScanSheet {
  return { id: "sheet-0", state: "submitting", ...overrides };
}

describe("summarizeSheets", () => {
  test("counts each sheet into exactly one bucket, matching the seeded statuses", () => {
    const sheets: ScanSheet[] = [
      sheet({
        id: "a",
        state: "submitted",
        result: {
          submissionId: "sub-a",
          status: "finalized",
          totalScore: 3,
          studentName: "A",
          nameFlagged: false,
          flaggedQuestionNumbers: [],
        },
      }),
      sheet({
        id: "b",
        state: "submitted",
        result: {
          submissionId: "sub-b",
          status: "needs_review",
          totalScore: null,
          studentName: "B",
          nameFlagged: false,
          flaggedQuestionNumbers: [2],
        },
      }),
      sheet({
        id: "c",
        state: "submitted",
        result: {
          submissionId: "sub-c",
          status: "needs_review",
          totalScore: null,
          studentName: "C",
          nameFlagged: false,
          flaggedQuestionNumbers: [1],
        },
      }),
      sheet({ id: "d", state: "failed", errorMessage: "network drop" }),
      sheet({ id: "e", state: "submitting" }),
    ];

    expect(summarizeSheets(sheets)).toEqual({
      attempted: 5,
      finalized: 1,
      needsReview: 2,
      failed: 1,
    });
  });

  test("an empty session summarizes to all zeros", () => {
    expect(summarizeSheets([])).toEqual({ attempted: 0, finalized: 0, needsReview: 0, failed: 0 });
  });
});

describe("needsReviewSubmissionIds", () => {
  test("returns exactly this session's needs_review submission ids, excluding finalized and failed sheets", () => {
    const sheets: ScanSheet[] = [
      sheet({
        id: "a",
        state: "submitted",
        result: {
          submissionId: "sub-a",
          status: "finalized",
          totalScore: 3,
          studentName: "A",
          nameFlagged: false,
          flaggedQuestionNumbers: [],
        },
      }),
      sheet({
        id: "b",
        state: "submitted",
        result: {
          submissionId: "sub-b",
          status: "needs_review",
          totalScore: null,
          studentName: "B",
          nameFlagged: false,
          flaggedQuestionNumbers: [2],
        },
      }),
      sheet({ id: "c", state: "failed" }),
    ];

    expect(needsReviewSubmissionIds(sheets)).toEqual(["sub-b"]);
  });
});
