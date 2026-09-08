import Link from "next/link";
import { listQuizzes } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import { Alert } from "@/components/Alert";
import { ReloadButton } from "@/components/ReloadButton";
import type { Quiz } from "@/lib/api/types";

export default async function ResultsPage() {
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
      loadError = true;
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="font-display text-2xl font-semibold text-olive-deep">Results</h1>

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
              <Link href={`/results/${quiz.id}`} className="block px-4 py-3 hover:bg-sand/40">
                {quiz.title}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
