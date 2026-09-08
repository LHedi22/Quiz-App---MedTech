import Link from "next/link";

/** Root 404 (web-app audit B8). Rendered inside the root layout. */
export default function NotFound() {
  return (
    <main className="flex flex-1 items-center justify-center p-8">
      <div className="max-w-md space-y-4 text-center" data-testid="not-found">
        <h1 className="font-display text-2xl font-semibold text-olive-deep">Page not found</h1>
        <p className="text-sm text-ink-soft">
          The page you&apos;re looking for doesn&apos;t exist or has moved.
        </p>
        <Link href="/quizzes" className="text-sm text-olive underline underline-offset-2">
          Back to quizzes
        </Link>
      </div>
    </main>
  );
}
