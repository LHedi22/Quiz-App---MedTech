import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { signOut } from "./actions";
import { NavLink } from "./NavLink";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <div className="flex flex-1 flex-col">
      <header className="flex items-center justify-between border-b border-sand px-6 py-4">
        <div className="flex items-center gap-8">
          <Link href="/quizzes" className="font-display text-lg font-semibold text-olive-deep">
            Exam Scanner
          </Link>
          <nav className="flex items-center gap-6 text-sm font-medium text-ink-soft">
            <NavLink href="/quizzes">Quizzes</NavLink>
            <NavLink href="/results">Results</NavLink>
            <NavLink href="/account">Account</NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-4 text-sm text-ink-soft">
          {user?.email && <span>{user.email}</span>}
          <form action={signOut}>
            <button type="submit" className="underline decoration-sand underline-offset-4 hover:text-ink hover:decoration-olive">
              Sign out
            </button>
          </form>
        </div>
      </header>
      <main className="flex-1 p-6">{children}</main>
    </div>
  );
}
