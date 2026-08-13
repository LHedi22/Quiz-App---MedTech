"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createQuiz, uploadQuizExcel, UploadValidationError } from "@/lib/api/client";
import { getAccessToken } from "@/lib/supabase/client";
import type { RowError } from "@/lib/api/types";

type Step = "title" | "upload";

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
      <h1 className="text-2xl font-semibold">New quiz</h1>

      {error && (
        <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {step === "title" && (
        <form onSubmit={handleCreateQuiz} className="space-y-4">
          <div className="space-y-1">
            <label htmlFor="title" className="block text-sm font-medium">
              Quiz title
            </label>
            <input
              id="title"
              name="title"
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-black px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            Create quiz
          </button>
        </form>
      )}

      {step === "upload" && (
        <div className="space-y-4">
          <form onSubmit={handleUpload} className="space-y-4">
            <div className="space-y-1">
              <label htmlFor="file" className="block text-sm font-medium">
                Excel file (questions, options, correct answers)
              </label>
              <input
                id="file"
                name="file"
                type="file"
                accept=".xlsx"
                required
                className="block w-full text-sm"
              />
            </div>
            <button
              type="submit"
              disabled={busy}
              className="rounded bg-black px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              Upload
            </button>
          </form>

          {rowErrors && rowErrors.length > 0 && (
            <div className="space-y-2 rounded border border-red-200 bg-red-50 p-4">
              <p className="text-sm font-medium text-red-700">
                Fix the following rows and upload again:
              </p>
              <ul className="space-y-1 text-sm text-red-700">
                {rowErrors.map((rowError) => (
                  <li key={rowError.row_number}>
                    Row {rowError.row_number}: {rowError.messages.join("; ")}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {questionsInserted !== null && (
            <div className="space-y-3 rounded border border-green-200 bg-green-50 p-4">
              <p className="text-sm text-green-800">
                {questionsInserted} question{questionsInserted === 1 ? "" : "s"} parsed and saved.
              </p>
              <button
                type="button"
                onClick={() => router.push(`/quizzes/${quizId}`)}
                className="rounded bg-black px-4 py-2 text-sm text-white"
              >
                Continue to generate versions
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
