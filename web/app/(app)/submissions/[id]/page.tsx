"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { correctAnswer, getSubmission } from "@/lib/api/client";
import { getAccessToken } from "@/lib/supabase/client";
import type { SubmissionDetail } from "@/lib/api/types";
import { Select } from "@/components/Select";
import { Button } from "@/components/Button";
import { Alert } from "@/components/Alert";
import { Bubble } from "@/components/Bubble";

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
    return <Alert tone="error">{error}</Alert>;
  }

  if (!submission) {
    return <p className="text-ink-soft">Loading…</p>;
  }

  const flaggedAnswers = submission.answers.filter((a) => a.flagged);
  const statusTone =
    submission.status === "finalized" ? "olive" : submission.status === "needs_review" ? "flag" : "outline";

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold text-olive-deep">
          Submission review
        </h1>
        <p className="text-sm text-ink-soft">
          Student: {submission.student_id ?? "—"} · Status:{" "}
          <span data-testid="submission-status" className="inline-flex items-center gap-2 font-mono text-ink">
            <Bubble tone={statusTone} size={7} />
            {submission.status}
          </span>
          {submission.total_score !== null && (
            <>
              {" "}
              · Score: <span className="font-mono text-ink">{submission.total_score}</span>
            </>
          )}
        </p>
      </div>

      {submission.status !== "needs_review" ? (
        <p className="flex items-center gap-2 text-olive-deep">
          <Bubble tone="olive" />
          This submission is finalized. Nothing left to review.
        </p>
      ) : (
        <div className="space-y-4" data-testid="flagged-answers">
          {flaggedAnswers.map((answer) => (
            <div
              key={answer.id}
              className="space-y-3 rounded-sm border border-flag/40 bg-flag-soft p-4"
              data-testid="flagged-answer"
              data-question-no={answer.question_no}
            >
              <p className="flex items-center gap-2 text-sm font-medium text-ink">
                <Bubble tone="flag" />
                Question {answer.question_no}
              </p>
              <p className="text-sm text-ink-soft">
                Detected: {answer.detected_option ?? "unclear"} (confidence{" "}
                <span className="font-mono">{answer.confidence.toFixed(2)}</span>)
              </p>
              <div className="flex items-center gap-3">
                <Select
                  label="Correct option"
                  id={`correct-${answer.id}`}
                  value={selections[answer.id] ?? ""}
                  onChange={(e) =>
                    setSelections((prev) => ({ ...prev, [answer.id]: e.target.value }))
                  }
                  wrapperClassName="flex items-center gap-2"
                >
                  <option value="" disabled>
                    Choose…
                  </option>
                  {OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </Select>
                <Button
                  type="button"
                  disabled={!selections[answer.id] || savingAnswerId === answer.id}
                  onClick={() => handleSave(answer.id)}
                >
                  Save
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Link href="/results" className="text-sm text-olive underline underline-offset-2">
        Back to results
      </Link>
    </div>
  );
}
