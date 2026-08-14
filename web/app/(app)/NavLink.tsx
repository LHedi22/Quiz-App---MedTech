"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bubble } from "@/components/Bubble";

/** Active-state indicator is a filled bubble, not a generic underline -
 * the same signature motif used for submission status everywhere else. */
export function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const active = pathname === href || pathname.startsWith(`${href}/`);

  return (
    <Link
      href={href}
      className={`inline-flex items-center gap-2 ${active ? "text-ink" : "hover:text-ink"}`}
    >
      {active && <Bubble tone="olive" size={6} />}
      {children}
    </Link>
  );
}
