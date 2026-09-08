import { createBrowserClient } from "@supabase/ssr";
import { AuthExpiredError } from "@/lib/authError";

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}

/** The backend API client (lib/api/) takes an explicit access token rather
 * than reaching into Supabase itself, so client components fetch it here.
 *
 * Throws `AuthExpiredError` (not a bare Error) when there is genuinely no
 * session, after one explicit refresh attempt - callers use
 * `handledAsAuthExpiry` to redirect to /login instead of dead-ending on a
 * generic "Could not load…" message. */
export async function getAccessToken(): Promise<string> {
  const supabase = createClient();

  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (session) {
    return session.access_token;
  }

  // getSession() auto-refreshes an expired access token, but if it returned
  // nothing the refresh token may still be salvageable - try once explicitly
  // before giving up.
  const {
    data: { session: refreshed },
  } = await supabase.auth.refreshSession();
  if (refreshed) {
    return refreshed.access_token;
  }

  throw new AuthExpiredError();
}
