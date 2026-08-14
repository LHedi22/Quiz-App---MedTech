"use client";

import { useState } from "react";
import { NavLink } from "./NavLink";

/** Collapses the header nav below the tablet breakpoint (Subtask 7c.1). The
 * desktop nav/user-menu in AppLayout are hidden via `md:flex`/`hidden` at
 * the same breakpoint, so exactly one of the two is ever visible/tappable. */
export function MobileNav({
  email,
  signOutAction,
}: {
  email?: string;
  signOutAction: () => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="md:hidden">
      <button
        type="button"
        aria-label="Toggle navigation"
        aria-expanded={open}
        data-testid="mobile-nav-toggle"
        onClick={() => setOpen((o) => !o)}
        className="flex h-9 w-9 items-center justify-center rounded-sm border border-sand text-ink-soft"
      >
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.5} className="h-5 w-5" aria-hidden>
          <path strokeLinecap="round" d="M3 5h14M3 10h14M3 15h14" />
        </svg>
      </button>

      {open && (
        <div
          data-testid="mobile-nav-panel"
          className="absolute inset-x-0 top-full z-10 space-y-4 border-b border-sand bg-paper px-4 py-4 shadow-sm"
        >
          <nav className="flex flex-col gap-4 text-sm font-medium text-ink-soft">
            <NavLink href="/quizzes">Quizzes</NavLink>
            <NavLink href="/results">Results</NavLink>
            <NavLink href="/scan">Scan</NavLink>
            <NavLink href="/account">Account</NavLink>
          </nav>
          <div className="flex items-center justify-between border-t border-sand pt-4 text-sm text-ink-soft">
            {email && <span className="truncate">{email}</span>}
            <form action={signOutAction}>
              <button
                type="submit"
                className="underline decoration-sand underline-offset-4 hover:text-ink hover:decoration-olive"
              >
                Sign out
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
