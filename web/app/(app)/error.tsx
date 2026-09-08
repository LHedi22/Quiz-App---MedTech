"use client";

import Link from "next/link";
import { Button } from "@/components/Button";

/** Route-level error boundary for the authenticated app (web-app audit B8).
 * Catches anything a page or its data fetch throws that isn't handled
 * inline, so the professor sees a recover-able state instead of Next's raw
 * error page. Copy is intentionally generic - refine later if needed. */
export default function AppError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="mx-auto max-w-md space-y-4 py-12 text-center" data-testid="route-error">
      <h1 className="font-display text-xl font-semibold text-olive-deep">Something went wrong</h1>
      <p className="text-sm text-ink-soft">
        We couldn&apos;t load this page. This is usually temporary.
      </p>
      <div className="flex items-center justify-center gap-3">
        <Button type="button" onClick={() => reset()}>
          Try again
        </Button>
        <Link href="/quizzes" className="text-sm text-olive underline underline-offset-2">
          Back to quizzes
        </Link>
      </div>
    </div>
  );
}
