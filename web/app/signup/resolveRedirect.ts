/** Decides where `signup` sends the professor after `supabase.auth.signUp`.
 * Pure so it can be unit-tested without importing the "use server" action.
 *
 * The key case (web-app audit B7): when the Supabase project requires email
 * confirmation, signUp succeeds with NO session - redirecting to /quizzes
 * would just bounce the sessionless user to /login and read as a failed
 * signup. */
interface SignUpResultShape {
  data: {
    session: unknown | null;
    user: { identities?: unknown[] | null } | null;
  };
  error: { message: string } | null;
}

export function resolveSignupRedirect(result: SignUpResultShape): string {
  if (result.error) {
    return `/signup?error=${encodeURIComponent(result.error.message)}`;
  }

  const { session, user } = result.data;
  if (session) {
    return "/quizzes";
  }

  // Supabase obfuscates "user already exists" as a success whose user has an
  // empty identities array - surface that rather than telling the professor
  // to check an email that will never arrive.
  if (user && (user.identities?.length ?? 0) === 0) {
    return `/signup?error=${encodeURIComponent(
      "An account with this email already exists. Try logging in.",
    )}`;
  }

  return "/signup?pending=1";
}
