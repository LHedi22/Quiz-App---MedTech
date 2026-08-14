import { createClient } from "@/lib/supabase/server";

export default async function AccountPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <div className="space-y-2">
      <h1 className="font-display text-2xl font-semibold text-olive-deep">Account</h1>
      <p className="text-ink-soft">{user?.email}</p>
    </div>
  );
}
