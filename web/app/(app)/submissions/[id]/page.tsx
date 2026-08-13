"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { correctAnswer, getSubmission } from "@/lib/api/client";
import { getAccessToken } from "@/lib/supabase/client";
import type { SubmissionDetail } from "@/lib/api/types";

const OPTIONS = ["A", "B", "C", "D"];

export default function SubmissionReviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: submissionId } = use(params);

  const [submission, setSubmission] = useState<SubmissionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selections, setSelections] = useState<Record<string, string>>({});
  const [savingAnswerId, setSavingAnswerId] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    (async () => {
      const token = await getAccessToken();
      const loaded = await getSubmission(submissionId, token);
      if (!ignore) setSubmission(loaded);
    })().catch(() => setError("Could not load this submission."));
    return () => {
      ignore = true;
    };
  }, [submissionId]);

  async function handleSave(answerId: string) {
    const correctOption = selections[answerId];
    if (!correctOption) return;

    setSavingAnswerId(answerId);
    setError(null);
    try {
      const token = await getAccessToken();
      // The PATCH response is the updated submission - used directly to
      // refresh local state, so the status/flagged-count change is visible
      // immediately without a manual page reload.
      const updated = await correctAnswer(submissionId, answerId, correctOption, token);
      setSubmission(updated);
    } catch {
      setError("Could not save the correction. Please try again.");
    } finally {
      setSavingAnswerId(null);
    }
  }

  if (error) {
    return (
      <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">
        {error}
      </p>
    );
  }

  if (!submission) {
    return <p className="text-gray-600">Loading…</p>;
  }

  const flaggedAnswers = submission.answers.filter((a) => a.flagged);

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Submission review</h1>
        <p className="text-sm text-gray-600">
          Student: {submission.student_id ?? "—"} · Status:{" "}
          <span data-testid="submission-status">{submission.status}</span>
          {submission.total_score !== null && <> · Score: {submission.total_score}</>}
        </p>
      </div>

      {submission.status !== "needs_review" ? (
        <p className="text-green-700">This submission is finalized. Nothing left to review.</p>
      ) : (
        <div className="space-y-4" data-testid="flagged-answers">
          {flaggedAnswers.map((answer) => (
            <div
              key={answer.id}
              className="space-y-3 rounded border border-yellow-300 bg-yellow-50 p-4"
              data-testid="flagged-answer"
              data-question-no={answer.question_no}
            >
              <p className="text-sm font-medium">Question {answer.question_no}</p>
              <p className="text-sm text-gray-600">
                Detected: {answer.detected_option ?? "unclear"} (confidence{" "}
                {answer.confidence.toFixed(2)})
              </p>
              <div className="flex items-center gap-3">
                <label htmlFor={`correct-${answer.id}`} className="text-sm font-medium">
                  Correct option
                </label>
                <select
                  id={`correct-${answer.id}`}
                  value={selections[answer.id] ?? ""}
                  onChange={(e) =>
                    setSelections((prev) => ({ ...prev, [answer.id]: e.target.value }))
                  }
                  className="rounded border border-gray-300 px-2 py-1 text-sm"
                >
                  <option value="" disabled>
                    Choose…
                  </option>
                  {OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  disabled={!selections[answer.id] || savingAnswerId === answer.id}
                  onClick={() => handleSave(answer.id)}
                  className="rounded bg-black px-3 py-1.5 text-sm text-white disabled:opacity-50"
                >
                  Save
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Link href="/results" className="text-sm underline">
        Back to results
      </Link>
    </div>
  );
}
