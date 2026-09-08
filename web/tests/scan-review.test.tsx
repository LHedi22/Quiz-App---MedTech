import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { SubmissionDetail } from "@/lib/api/types";

const getSubmission = vi.fn();
let searchParams = new URLSearchParams();

vi.mock("@/lib/api/client", () => ({
  getSubmission: (...args: unknown[]) => getSubmission(...args),
}));

vi.mock("@/lib/supabase/client", () => ({
  getAccessToken: () => Promise.resolve("test-token"),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParams,
}));

import ScanReviewPage from "@/app/(app)/scan/review/page";

function submission(id: string): SubmissionDetail {
  return {
    id,
    version_id: "v1",
    student_id: id,
    student_name: `Student ${id}`,
    name_confidence: 95,
    name_flagged: false,
    name_manually_edited: false,
    total_score: 3,
    status: "needs_review",
    created_at: "2026-08-31T10:00:00Z",
    answers: [],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParams = new URLSearchParams();
});

afterEach(() => {
  cleanup();
});

describe("scan review list — partial failure", () => {
  it("renders the submissions that loaded and notes the ones that didn't", async () => {
    searchParams = new URLSearchParams({ ids: "s1,s2,s3" });
    getSubmission.mockImplementation((id: string) =>
      id === "s2" ? Promise.reject(new Error("404")) : Promise.resolve(submission(id)),
    );

    render(<ScanReviewPage />);

    await waitFor(() => expect(screen.getAllByTestId("scan-review-item")).toHaveLength(2));
    expect(screen.getByTestId("partial-load-note").textContent).toMatch(
      /1 submission from this session could not be loaded/i,
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a distinct empty state when every id fails, not 'nothing needs review'", async () => {
    searchParams = new URLSearchParams({ ids: "s1,s2" });
    getSubmission.mockRejectedValue(new Error("gone"));

    render(<ScanReviewPage />);

    await waitFor(() =>
      expect(screen.getByTestId("empty-state").textContent).toMatch(
        /none of this session's submissions could be loaded/i,
      ),
    );
    expect(screen.getByTestId("partial-load-note")).toBeTruthy();
  });

  it("shows the normal empty state when there are no ids at all", async () => {
    render(<ScanReviewPage />);

    await waitFor(() =>
      expect(screen.getByTestId("empty-state").textContent).toMatch(/nothing from this session/i),
    );
    expect(getSubmission).not.toHaveBeenCalled();
  });
});
