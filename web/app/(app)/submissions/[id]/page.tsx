"use client";

import { use, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { correctAnswer, correctName, getSubmission } from "@/lib/api/client";
import { getAccessToken } from "@/lib/supabase/client";
import { handledAsAuthExpiry } from "@/lib/authError";
import type { AnswerDetail, SubmissionDetail } from "@/lib/api/types";
import { Select } from "@/components/Select";
import { Field } from "@/components/Field";
import { Button } from "@/components/Button";
import { Alert } from "@/components/Alert";
import { Bubble } from "@/components/Bubble";
import { StatusBadge } from "@/components/StatusBadge";

const OPTIONS = ["A", "B", "C", "D"];
const BLANK = ""; // <select> value standing for "student left this blank"

/** Flagged answers first (they still need a decision), then by question
 * number. Same array feeds the whole sheet, so nothing can drift. */
function orderAnswers(answers: AnswerDetail[]): AnswerDetail[] {
  return [...answers].sort((a, b) => {
    if (a.flagged !== b.flagged) return a.flagged ? -1 : 1;
    return a.question_no - b.question_no;
  });
}

export default function SubmissionReviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: submissionId } = use(params);

  const [submission, setSubmission] = useState<SubmissionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Per-answer draft option: the value currently shown in that row's <select>,
  // seeded from what was detected/last saved. "" = blank.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingAnswerId, setSavingAnswerId] = useState<string | null>(null);
  const [nameInput, setNameInput] = useState("");
  const [savingName, setSavingName] = useState(false);

  function syncFromSubmission(loaded: SubmissionDetail) {
    setSubmission(loaded);
    setNameInput(loaded.student_name ?? "");
    setDrafts(
      Object.fromEntries(
        loaded.answers.map((a) => [a.id, a.detected_option ?? BLANK]),
      ),
    );
  }

  useEffect(() => {
    let ignore = false;
    (async () => {
      const token = await getAccessToken();
      const loaded = await getSubmission(submissionId, token);
      if (!ignore) syncFromSubmission(loaded);
    })().catch((e) => {
      if (handledAsAuthExpiry(e)) return;
      setError("Could not load this submission.");
    });
    return () => {
      ignore = true;
    };
  }, [submissionId]);

  const orderedAnswers = useMemo(
    () => (submission ? orderAnswers(submission.answers) : []),
    [submission],
  );

  async function handleSaveName() {
    if (!nameInput.trim()) return;
    setSavingName(true);
    setError(null);
    try {
      const token = await getAccessToken();
      syncFromSubmission(await correctName(submissionId, nameInput, token));
    } catch (e) {
      if (handledAsAuthExpiry(e)) return;
      setError("Could not save the name correction. Please try again.");
    } finally {
      setSavingName(false);
    }
  }

  async function handleSaveAnswer(answer: AnswerDetail) {
    const draft = drafts[answer.id] ?? BLANK;
    setSavingAnswerId(answer.id);
    setError(null);
    try {
      const token = await getAccessToken();
      // The PATCH response is the full updated submission - status, score
      // and per-answer flags all refresh in place, no reload.
      const updated = await correctAnswer(
        submissionId,
        answer.id,
        draft === BLANK ? null : draft,
        token,
      );
      syncFromSubmission(updated);
    } catch (e) {
      if (handledAsAuthExpiry(e)) return;
      setError("Could not save the correction. Please try again.");
    } finally {
      setSavingAnswerId(null);
    }
  }

  if (error && !submission) {
    return <Alert tone="error">{error}</Alert>;
  }
  if (!submission) {
    return <p className="text-ink-soft">Loading…</p>;
  }

  const flaggedCount = submission.answers.filter((a) => a.flagged).length;
  const answeredKey = (a: AnswerDetail) => a.key_option ?? "—";

  return (
    <div className="max-w-3xl space-y-6">
      <div className="space-y-1">
        <h1 className="font-display text-2xl font-semibold text-olive-deep">
          Submission
        </h1>
        <p className="text-sm text-ink-soft">
          Student: {submission.name_flagged && <Bubble tone="flag" size={7} />}
          <span className="text-ink">
            {submission.student_name ?? submission.student_id ?? "—"}
          </span>
          {submission.name_manually_edited && " (edited)"} · Status:{" "}
          <span data-testid="submission-status" className="font-mono text-ink">
            {submission.status}
          </span>{" "}
          · Score:{" "}
          <span className="font-mono text-ink">
            {submission.total_score !== null ? submission.total_score : "—"}
          </span>
        </p>
        <p className="flex items-center gap-2 text-sm">
          <StatusBadge status={submission.status} />
          {submission.status === "needs_review" && (
            <span className="text-ink-soft">
              — {flaggedCount + (submission.name_flagged ? 1 : 0)} item
              {flaggedCount + (submission.name_flagged ? 1 : 0) === 1
                ? ""
                : "s"}{" "}
              to resolve
            </span>
          )}
        </p>
      </div>

      {error && <Alert tone="error">{error}</Alert>}

      {submission.status !== "needs_review" && (
        <p className="flex items-center gap-2 text-olive-deep">
          <Bubble tone="olive" />
          This submission is finalized. You can still change any answer below.
        </p>
      )}

      {/* Student name — editable at any time, with a prominent prompt when
          the scan's OCR read was flagged. */}
      <section
        className={`space-y-3 rounded-sm border p-4 ${
          submission.name_flagged
            ? "border-flag/40 bg-flag-soft"
            : "border-sand bg-paper-raised"
        }`}
        data-testid={submission.name_flagged ? "flagged-name" : "name-editor"}
      >
        <p className="flex items-center gap-2 text-sm font-medium text-ink">
          {submission.name_flagged && <Bubble tone="flag" />}
          Student name
        </p>
        {submission.name_flagged && (
          <p className="text-sm text-ink-soft">
            Detected: {submission.student_name || "unclear"}
            {submission.name_confidence !== null && (
              <>
                {" "}
                (confidence{" "}
                <span className="font-mono">
                  {submission.name_confidence.toFixed(1)}
                </span>
                )
              </>
            )}
          </p>
        )}
        <div className="flex flex-wrap items-end gap-3">
          <Field
            label={submission.name_flagged ? "Correct name" : "Name"}
            id="student-name-correction"
            value={nameInput}
            onChange={(e) => setNameInput(e.target.value)}
          />
          <Button
            type="button"
            disabled={
              !nameInput.trim() ||
              savingName ||
              nameInput.trim() === (submission.student_name ?? "")
            }
            onClick={handleSaveName}
          >
            Save
          </Button>
        </div>
      </section>

      {/* Full answer sheet: every question, always editable. Flagged rows
          sit at the top and are highlighted. */}
      <section className="space-y-3" data-testid="answer-sheet">
        <h2 className="font-display text-lg font-semibold text-olive-deep">
          Answers ({submission.answers.length})
        </h2>

        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-sand text-ink-soft">
                <th className="py-2 pr-3 font-medium">#</th>
                <th className="py-2 pr-3 font-medium">Question</th>
                <th className="py-2 pr-3 font-medium">Marked</th>
                <th className="py-2 pr-3 font-medium">Key</th>
                <th className="py-2 pr-3 font-medium">Result</th>
                <th className="py-2 pr-3 font-medium">Change to</th>
                <th className="py-2 pr-3"></th>
              </tr>
            </thead>
            <tbody>
              {orderedAnswers.map((answer) => {
                const draft = drafts[answer.id] ?? BLANK;
                const current = answer.detected_option ?? BLANK;
                const dirty = draft !== current;
                return (
                  <tr
                    key={answer.id}
                    data-testid={
                      answer.flagged ? "flagged-answer" : "answer-row"
                    }
                    data-question-no={answer.question_no}
                    className={`border-b border-sand/60 align-top ${
                      answer.flagged ? "bg-flag-soft" : ""
                    }`}
                  >
                    <td className="py-2 pr-3 font-mono text-ink-soft">
                      {answer.question_no}
                    </td>
                    <td className="py-2 pr-3 text-ink-soft">
                      <span className="line-clamp-2 max-w-xs">
                        {answer.question_text ?? "—"}
                      </span>
                    </td>
                    <td className="py-2 pr-3">
                      <span className="inline-flex items-center gap-1.5">
                        {answer.flagged && <Bubble tone="flag" size={7} />}
                        <span className="font-mono text-ink">
                          {answer.detected_option ?? "blank"}
                        </span>
                        {answer.manually_edited && (
                          <span
                            className="text-xs text-ink-soft"
                            data-testid="answer-edited-badge"
                          >
                            (edited)
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="py-2 pr-3 font-mono text-ink-soft">
                      {answeredKey(answer)}
                    </td>
                    <td className="py-2 pr-3">
                      {answer.flagged ? (
                        <span className="text-ink-soft">
                          flagged
                          <span className="ml-1 font-mono text-xs">
                            ({answer.confidence.toFixed(2)})
                          </span>
                        </span>
                      ) : answer.correct ? (
                        <span className="text-olive-deep">correct</span>
                      ) : (
                        <span className="text-flag">wrong</span>
                      )}
                    </td>
                    <td className="py-2 pr-3">
                      <Select
                        label="Correct option"
                        id={`correct-${answer.id}`}
                        labelProps={{ className: "sr-only" }}
                        value={draft}
                        onChange={(e) =>
                          setDrafts((prev) => ({
                            ...prev,
                            [answer.id]: e.target.value,
                          }))
                        }
                      >
                        <option value={BLANK}>Blank / unanswered</option>
                        {OPTIONS.map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                      </Select>
                    </td>
                    <td className="py-2 pr-3">
                      <Button
                        type="button"
                        variant="secondary"
                        disabled={
                          savingAnswerId === answer.id ||
                          (!dirty && !answer.flagged)
                        }
                        onClick={() => handleSaveAnswer(answer)}
                      >
                        Save
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <Link
        href="/results"
        className="text-sm text-olive underline underline-offset-2"
      >
        Back to results
      </Link>
    </div>
  );
}
