import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import type { VersionSummary } from "@/lib/api/types";

const listQuizVersions = vi.fn();
const getVersionPdfUrl = vi.fn();
const createVersions = vi.fn();

vi.mock("@/lib/api/client", () => ({
  listQuizVersions: (...args: unknown[]) => listQuizVersions(...args),
  getVersionPdfUrl: (...args: unknown[]) => getVersionPdfUrl(...args),
  createVersions: (...args: unknown[]) => createVersions(...args),
}));

vi.mock("@/lib/supabase/client", () => ({
  getAccessToken: () => Promise.resolve("test-token"),
}));

import QuizDetailPage from "@/app/(app)/quizzes/[id]/page";

function settled<T>(value: T): Promise<T> {
  const p = Promise.resolve(value) as Promise<T> & { status: string; value: T };
  p.status = "fulfilled";
  p.value = value;
  return p;
}

function version(n: number): VersionSummary {
  return { id: `v${n}`, version_number: n };
}

function renderPage() {
  return render(<QuizDetailPage params={settled({ id: "quiz-1" })} />);
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

describe("quiz detail — versions list", () => {
  it("renders every version even when one PDF URL fails, with a per-row retry and no page error", async () => {
    listQuizVersions.mockResolvedValue([version(1), version(2), version(3)]);
    getVersionPdfUrl.mockImplementation((versionId: string) =>
      versionId === "v2"
        ? Promise.reject(new Error("signed url 500"))
        : Promise.resolve({ url: `https://storage.example/${versionId}.pdf` }),
    );

    renderPage();

    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(3));

    // The two good rows have download links, the failed one has a retry.
    expect(screen.getAllByTestId("download-pdf")).toHaveLength(2);
    const failedRow = screen.getByTestId("retry-pdf").closest("li")!;
    expect(failedRow.getAttribute("data-version-id")).toBe("v2");

    // No page-level error banner.
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("recovers a failed row when its retry succeeds on a second attempt", async () => {
    listQuizVersions.mockResolvedValue([version(1)]);
    let attempt = 0;
    getVersionPdfUrl.mockImplementation(() => {
      attempt += 1;
      return attempt === 1
        ? Promise.reject(new Error("transient"))
        : Promise.resolve({ url: "https://storage.example/v1.pdf" });
    });

    renderPage();

    const retry = await screen.findByTestId("retry-pdf");
    retry.click();

    await waitFor(() => expect(screen.getByTestId("download-pdf")).toBeTruthy());
    expect(screen.queryByTestId("retry-pdf")).toBeNull();
  });

  it("still lists versions that loaded even though it can't yet fetch their URLs", async () => {
    listQuizVersions.mockResolvedValue([version(1), version(2)]);
    getVersionPdfUrl.mockRejectedValue(new Error("storage down"));

    renderPage();

    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(2));
    expect(screen.getAllByTestId("retry-pdf")).toHaveLength(2);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the page error only when the version list itself fails to load", async () => {
    listQuizVersions.mockRejectedValue(new Error("list 500"));

    renderPage();

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/could not load versions/i)).toBeTruthy();
  });
});
