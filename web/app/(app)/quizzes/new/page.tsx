"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createQuiz, uploadQuizExcel, UploadValidationError } from "@/lib/api/client";
import { getAccessToken } from "@/lib/supabase/client";
import type { RowError } from "@/lib/api/types";
import { Field } from "@/components/Field";
import { Button } from "@/components/Button";
import { Alert } from "@/components/Alert";

type Step = "title" | "upload";

const STEPS: { key: Step; label: string }[] = [
  { key: "title", label: "Title" },
  { key: "upload", label: "Upload" },
];

export default function NewQuizPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("title");
  const [title, setTitle] = useState("");
  const [quizId, setQuizId] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<RowError[] | null>(null);
  const [questionsInserted, setQuestionsInserted] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleCreateQuiz(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const token = await getAccessToken();
      const quiz = await createQuiz(title, token);
      setQuizId(quiz.id);
      setStep("upload");
    } catch {
      setError("Could not create the quiz. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleUpload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!quizId) return;
    const fileInput = e.currentTarget.elements.namedItem("file") as HTMLInputElement;
    const file = fileInput.files?.[0];
    if (!file) {
      setError("Choose an Excel file first.");
      return;
    }

    setError(null);
    setRowErrors(null);
    setBusy(true);
    try {
      const token = await getAccessToken();
      const result = await uploadQuizExcel(quizId, file, token);
      setQuestionsInserted(result.questions_inserted);
    } catch (err) {
      if (err instanceof UploadValidationError) {
        setRowErrors(err.errors);
      } else {
        setError("Upload failed. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="font-display text-2xl font-semibold text-olive-deep">New quiz</h1>

      <ol className="flex items-center gap-4 text-sm">
        {STEPS.map((s, i) => {
          const isCurrent = s.key === step;
          const isDone = STEPS.findIndex((x) => x.key === step) > i;
          return (
            <li key={s.key} className="flex items-center gap-2">
              <span
                className={`flex h-6 w-6 items-center justify-center rounded-full font-mono text-xs ${
                  isCurrent || isDone
                    ? "bg-olive text-paper"
                    : "border border-sand text-ink-soft"
                }`}
              >
                {i + 1}
              </span>
              <span className={isCurrent ? "font-medium text-ink" : "text-ink-soft"}>
                {s.label}
              </span>
            </li>
          );
        })}
      </ol>

      {error && <Alert tone="error">{error}</Alert>}

      {step === "title" && (
        <form onSubmit={handleCreateQuiz} className="space-y-4">
          <Field
            label="Quiz title"
            id="title"
            name="title"
            type="text"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <Button type="submit" disabled={busy}>
            Create quiz
          </Button>
        </form>
      )}

      {step === "upload" && (
        <div className="space-y-4">
          <form onSubmit={handleUpload} className="space-y-4">
            <div className="space-y-1">
              <label htmlFor="file" className="block text-sm font-medium text-ink">
                Excel file (questions, options, correct answers)
              </label>
              <input
                id="file"
                name="file"
                type="file"
                accept=".xlsx"
                required
                className="block w-full text-sm text-ink-soft file:mr-3 file:rounded-sm file:border-0 file:bg-sand file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-olive-deep"
              />
            </div>
            <Button type="submit" disabled={busy}>
              Upload
            </Button>
          </form>

          {rowErrors && rowErrors.length > 0 && (
            <Alert tone="error">
              <p className="font-medium">Fix the following rows and upload again:</p>
              <ul className="mt-2 space-y-1">
                {rowErrors.map((rowError) => (
                  <li key={rowError.row_number}>
                    Row {rowError.row_number}: {rowError.messages.join("; ")}
                  </li>
                ))}
              </ul>
            </Alert>
          )}

          {questionsInserted !== null && (
            <Alert tone="success">
              <div className="space-y-3">
                <p>
                  {questionsInserted} question{questionsInserted === 1 ? "" : "s"} parsed and
                  saved.
                </p>
                <Button type="button" onClick={() => router.push(`/quizzes/${quizId}`)}>
                  Continue to generate versions
                </Button>
              </div>
            </Alert>
          )}
        </div>
      )}
    </div>
  );
}
