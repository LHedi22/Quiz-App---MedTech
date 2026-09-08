/** Thrown when the professor's session is gone (no Supabase session, or the
 * backend rejected the token with 401) during a client-side action. Distinct
 * from a generic request failure so the UI can send the user to /login
 * instead of showing a dead-end "Could not load…" message.
 *
 * Kept dependency-free so both `lib/supabase/client.ts` and
 * `lib/api/client.ts` can throw it without importing each other. */
export class AuthExpiredError extends Error {
  constructor() {
    super("Your session has expired. Please sign in again.");
    this.name = "AuthExpiredError";
  }
}

/** Shared catch helper. If `error` is an expired session, kick off a
 * client-side redirect to /login and return true so the caller stops
 * (skips its own error UI). Returns false for anything else, which the
 * caller should then handle normally. No-ops the redirect on the server. */
export function handledAsAuthExpiry(error: unknown): boolean {
  if (error instanceof AuthExpiredError) {
    if (typeof window !== "undefined") {
      // A hard navigation on purpose: the session is gone, so a full reload
      // is the clean way to drop all stale client state (React Query caches,
      // form drafts, the Supabase client's in-memory session) rather than a
      // soft router.push that would keep it around.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign("/login");
    }
    return true;
  }
  return false;
}
