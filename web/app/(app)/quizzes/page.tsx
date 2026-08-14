import Link from "next/link";
import { listQuizzes } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";

export default async function QuizzesPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const quizzes = session ? await listQuizzes(session.access_token) : [];

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

      {quizzes.length === 0 ? (
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
