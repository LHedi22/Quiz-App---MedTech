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
        <h1 className="text-2xl font-semibold">Quizzes</h1>
        <Link href="/quizzes/new" className="rounded bg-black px-4 py-2 text-sm text-white">
          New quiz
        </Link>
      </div>

      {quizzes.length === 0 ? (
        <p className="text-gray-600">No quizzes yet.</p>
      ) : (
        <ul className="divide-y divide-gray-200 rounded border border-gray-200">
          {quizzes.map((quiz) => (
            <li key={quiz.id}>
              <Link
                href={`/quizzes/${quiz.id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-gray-50"
              >
                <span>{quiz.title}</span>
                <span className="text-sm text-gray-500">
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
