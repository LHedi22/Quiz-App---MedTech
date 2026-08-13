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
      <h1 className="text-2xl font-semibold">Results</h1>

      {quizzes.length === 0 ? (
        <p className="text-gray-600">No quizzes yet.</p>
      ) : (
        <ul className="divide-y divide-gray-200 rounded border border-gray-200">
          {quizzes.map((quiz) => (
            <li key={quiz.id}>
              <Link
                href={`/results/${quiz.id}`}
                className="block px-4 py-3 hover:bg-gray-50"
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
