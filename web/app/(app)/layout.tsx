import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { signOut } from "./actions";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <div className="flex flex-1 flex-col">
      <header className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
        <nav className="flex items-center gap-6 text-sm font-medium">
          <Link href="/quizzes">Quizzes</Link>
          <Link href="/results">Results</Link>
          <Link href="/account">Account</Link>
        </nav>
        <div className="flex items-center gap-4 text-sm text-gray-600">
          {user?.email && <span>{user.email}</span>}
          <form action={signOut}>
            <button type="submit" className="underline">
              Sign out
            </button>
          </form>
        </div>
      </header>
      <main className="flex-1 p-6">{children}</main>
    </div>
  );
}
