import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import type { SubmissionDetail } from "@/lib/api/types";

const getSubmission = vi.fn();
const correctAnswer = vi.fn();
const correctName = vi.fn();

vi.mock("@/lib/api/client", () => ({
  getSubmission: (...args: unknown[]) => getSubmission(...args),
  correctAnswer: (...args: unknown[]) => correctAnswer(...args),
  correctName: (...args: unknown[]) => correctName(...args),
}));

vi.mock("@/lib/supabase/client", () => ({
  getAccessToken: () => Promise.resolve("test-token"),
}));

import SubmissionReviewPage from "@/app/(app)/submissions/[id]/page";

type Answer = SubmissionDetail["answers"][number];

function answer(over: Partial<Answer> = {}): Answer {
  return {
    id: "a1",
    question_no: 1,
    detected_option: "A",
    confidence: 0.99,
    flagged: false,
    correct: true,
    score: 1,
    question_text: "What is 2+2?",
    key_option: "A",
    manually_edited: false,
    edited_at: null,
    ...over,
  };
}

function submission(over: Partial<SubmissionDetail> = {}): SubmissionDetail {
  return {
    id: "s1",
    version_id: "v1",
    student_id: "stu-1",
    student_name: "Grace Hopper",
    name_confidence: 95,
    name_flagged: false,
    name_manually_edited: false,
    total_score: 3,
    status: "finalized",
    created_at: "2026-08-31T10:00:00Z",
    answers: [
      answer({
        id: "a1",
        question_no: 1,
        detected_option: "A",
        correct: true,
        score: 1,
      }),
      answer({
        id: "a2",
        question_no: 2,
        detected_option: "C",
        key_option: "B",
        correct: false,
        score: 0,
      }),
      answer({
        id: "a3",
        question_no: 3,
        detected_option: "D",
        key_option: "D",
        correct: true,
        score: 1,
      }),
    ],
    ...over,
  };
}

/** React's `use()` returns synchronously (no Suspense) for a promise that
 * already carries the fulfilled-status shape it looks for internally. */
function settled<T>(value: T): Promise<T> {
  const p = Promise.resolve(value) as Promise<T> & { status: string; value: T };
  p.status = "fulfilled";
  p.value = value;
  return p;
}

function renderPage() {
  return render(<SubmissionReviewPage params={settled({ id: "s1" })} />);
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

describe("submission review — full answer sheet", () => {
  it("shows every answer on a finalized submission, not just flagged ones", async () => {
    getSubmission.mockResolvedValue(submission());
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("answer-sheet")).toBeInTheDocument(),
    );
    expect(screen.getAllByTestId("answer-row")).toHaveLength(3);
    expect(
      screen.getByText(
        "This submission is finalized. You can still change any answer below.",
      ),
    ).toBeInTheDocument();
    const rows = screen.getAllByTestId("answer-row");
    const q2Row = rows.find((r) => r.getAttribute("data-question-no") === "2")!;
    expect(within(q2Row).getByText("wrong")).toBeInTheDocument();
  });

  it("edits a non-flagged answer and refreshes from the response", async () => {
    getSubmission.mockResolvedValue(submission());
    const updated = submission({
      total_score: 2,
      answers: [
        answer({
          id: "a1",
          question_no: 1,
          detected_option: "B",
          correct: false,
          score: 0,
          manually_edited: true,
          edited_at: "2026-08-31T11:00:00Z",
        }),
        answer({
          id: "a2",
          question_no: 2,
          detected_option: "C",
          key_option: "B",
          correct: false,
          score: 0,
        }),
        answer({
          id: "a3",
          question_no: 3,
          detected_option: "D",
          key_option: "D",
          correct: true,
          score: 1,
        }),
      ],
    });
    correctAnswer.mockResolvedValue(updated);

    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("answer-sheet")).toBeInTheDocument(),
    );

    const rows = screen.getAllByTestId("answer-row");
    const q1Row = rows.find((r) => r.getAttribute("data-question-no") === "1")!;
    fireEvent.change(within(q1Row).getByLabelText("Correct option"), {
      target: { value: "B" },
    });
    fireEvent.click(within(q1Row).getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(correctAnswer).toHaveBeenCalledWith("s1", "a1", "B", "test-token"),
    );
    await waitFor(() =>
      expect(screen.getByTestId("answer-edited-badge")).toBeInTheDocument(),
    );
  });

  it("can blank an answer (sends null)", async () => {
    getSubmission.mockResolvedValue(submission());
    correctAnswer.mockResolvedValue(submission());
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("answer-sheet")).toBeInTheDocument(),
    );

    const rows = screen.getAllByTestId("answer-row");
    const q3Row = rows.find((r) => r.getAttribute("data-question-no") === "3")!;
    fireEvent.change(within(q3Row).getByLabelText("Correct option"), {
      target: { value: "" },
    });
    fireEvent.click(within(q3Row).getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(correctAnswer).toHaveBeenCalledWith(
        "s1",
        "a3",
        null,
        "test-token",
      ),
    );
  });

  it("keeps the flagged-answer affordance for needs_review submissions", async () => {
    getSubmission.mockResolvedValue(
      submission({
        status: "needs_review",
        total_score: null,
        answers: [
          answer({
            id: "a1",
            question_no: 1,
            detected_option: null,
            flagged: true,
            correct: null,
            score: null,
          }),
          answer({
            id: "a2",
            question_no: 2,
            detected_option: "B",
            key_option: "B",
            correct: true,
            score: 1,
          }),
        ],
      }),
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("answer-sheet")).toBeInTheDocument(),
    );

    expect(screen.getAllByTestId("flagged-answer")).toHaveLength(1);
    expect(screen.getByTestId("submission-status")).toHaveTextContent(
      "needs_review",
    );
  });

  it("edits the student name at any time and marks it edited", async () => {
    getSubmission.mockResolvedValue(submission());
    correctName.mockResolvedValue(
      submission({
        student_name: "Grace M. Hopper",
        name_manually_edited: true,
      }),
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("answer-sheet")).toBeInTheDocument(),
    );

    const nameEditor = screen.getByTestId("name-editor");
    fireEvent.change(within(nameEditor).getByLabelText("Name"), {
      target: { value: "Grace M. Hopper" },
    });
    fireEvent.click(within(nameEditor).getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(correctName).toHaveBeenCalledWith(
        "s1",
        "Grace M. Hopper",
        "test-token",
      ),
    );
    await waitFor(() =>
      expect(screen.getByText(/\(edited\)/)).toBeInTheDocument(),
    );
  });
});
