import Link from "next/link";
import { signup } from "./actions";
import { Field } from "@/components/Field";
import { Button } from "@/components/Button";
import { Alert } from "@/components/Alert";
import { Bubble } from "@/components/Bubble";

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; pending?: string }>;
}) {
  const { error, pending } = await searchParams;

  return (
    <main className="flex flex-1 items-center justify-center p-8">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex items-center gap-2">
          <Bubble tone="outline" size={10} />
          <Bubble tone="olive" size={10} />
          <Bubble tone="outline" size={10} />
        </div>
        <h1 className="font-display text-2xl font-semibold text-olive-deep">Sign up</h1>

        {pending ? (
          <div className="space-y-4" data-testid="signup-pending">
            <Alert tone="success">
              Check your email to confirm your account, then sign in.
            </Alert>
            <p className="text-sm text-ink-soft">
              <Link href="/login" className="text-olive underline underline-offset-2">
                Go to log in
              </Link>
            </p>
          </div>
        ) : (
          <>
            {error && <Alert tone="error">{error}</Alert>}
            <form className="space-y-4">
              <Field label="Email" id="email" name="email" type="email" required />
              <Field
                label="Password"
                id="password"
                name="password"
                type="password"
                required
                minLength={6}
              />
              <Button formAction={signup} type="submit" className="w-full">
                Sign up
              </Button>
            </form>
            <p className="text-sm text-ink-soft">
              Already have an account?{" "}
              <Link href="/login" className="text-olive underline underline-offset-2">
                Log in
              </Link>
            </p>
          </>
        )}
      </div>
    </main>
  );
}
