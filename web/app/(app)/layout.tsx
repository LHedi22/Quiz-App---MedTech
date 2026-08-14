import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { signOut } from "./actions";
import { NavLink } from "./NavLink";
import { MobileNav } from "./MobileNav";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <div className="flex flex-1 flex-col">
      <header className="relative flex items-center justify-between border-b border-sand px-4 py-4 sm:px-6">
        <div className="flex items-center gap-8">
          <Link href="/quizzes" className="font-display text-lg font-semibold text-olive-deep">
            Exam Scanner
          </Link>
          <nav className="hidden items-center gap-6 text-sm font-medium text-ink-soft md:flex">
            <NavLink href="/quizzes">Quizzes</NavLink>
            <NavLink href="/results">Results</NavLink>
            <NavLink href="/scan">Scan</NavLink>
            <NavLink href="/account">Account</NavLink>
          </nav>
        </div>
        <div className="hidden items-center gap-4 text-sm text-ink-soft md:flex">
          {user?.email && <span>{user.email}</span>}
          <form action={signOut}>
            <button type="submit" className="underline decoration-sand underline-offset-4 hover:text-ink hover:decoration-olive">
              Sign out
            </button>
          </form>
        </div>
        <MobileNav email={user?.email} signOutAction={signOut} />
      </header>
      <main className="flex-1 p-4 sm:p-6">{children}</main>
    </div>
  );
}
