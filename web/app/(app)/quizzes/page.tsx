import Link from "next/link";
import { listQuizzes } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import { Alert } from "@/components/Alert";
import { ReloadButton } from "@/components/ReloadButton";
import type { Quiz } from "@/lib/api/types";

export default async function QuizzesPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  let quizzes: Quiz[] = [];
  let loadError = false;
  if (session) {
    try {
      quizzes = await listQuizzes(session.access_token);
    } catch {
      // Keep the page shell; show a recover-able inline error rather than
      // throwing the whole segment to the error boundary (web-app audit B8).
      loadError = true;
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-semibold text-olive-deep">Quizzes</h1>
        <Link
          href="/quizzes/new"
          className="rounded-sm bg-olive px-4 py-2 text-sm font-medium text-paper hover:bg-olive-deep"
        >
          New quiz
        </Link>
      </div>

      {loadError ? (
        <div className="space-y-3" data-testid="load-error">
          <Alert tone="error">Could not load your quizzes. This is usually temporary.</Alert>
          <ReloadButton />
        </div>
      ) : quizzes.length === 0 ? (
        <p className="text-ink-soft">No quizzes yet.</p>
      ) : (
        <ul className="divide-y divide-sand rounded-sm border border-sand bg-paper-raised">
          {quizzes.map((quiz) => (
            <li key={quiz.id}>
              <Link
                href={`/quizzes/${quiz.id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-sand/40"
              >
                <span>{quiz.title}</span>
                <span className="font-mono text-xs text-ink-soft">
                  {new Date(quiz.created_at).toLocaleDateString()}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
