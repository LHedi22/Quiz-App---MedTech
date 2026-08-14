import Link from "next/link";
import { login } from "./actions";
import { Field } from "@/components/Field";
import { Button } from "@/components/Button";
import { Alert } from "@/components/Alert";
import { Bubble } from "@/components/Bubble";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;

  return (
    <main className="flex flex-1 items-center justify-center p-8">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex items-center gap-2">
          <Bubble tone="olive" size={10} />
          <Bubble tone="outline" size={10} />
          <Bubble tone="outline" size={10} />
        </div>
        <h1 className="font-display text-2xl font-semibold text-olive-deep">Log in</h1>
        {error && <Alert tone="error">{error}</Alert>}
        <form className="space-y-4">
          <Field label="Email" id="email" name="email" type="email" required />
          <Field label="Password" id="password" name="password" type="password" required />
          <Button formAction={login} type="submit" className="w-full">
            Log in
          </Button>
        </form>
        <p className="text-sm text-ink-soft">
          No account?{" "}
          <Link href="/signup" className="text-olive underline underline-offset-2">
            Sign up
          </Link>
        </p>
      </div>
    </main>
  );
}
