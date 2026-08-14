import Link from "next/link";
import { listQuizzes } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";

export default async function ResultsPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const quizzes = session ? await listQuizzes(session.access_token) : [];

  return (
    <div className="space-y-6">
      <h1 className="font-display text-2xl font-semibold text-olive-deep">Results</h1>

      {quizzes.length === 0 ? (
        <p className="text-ink-soft">No quizzes yet.</p>
      ) : (
        <ul className="divide-y divide-sand rounded-sm border border-sand bg-paper-raised">
          {quizzes.map((quiz) => (
            <li key={quiz.id}>
              <Link
                href={`/results/${quiz.id}`}
                className="block px-4 py-3 hover:bg-sand/40"
              >
                {quiz.title}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
