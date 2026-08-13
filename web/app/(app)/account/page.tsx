import { createClient } from "@/lib/supabase/server";

export default async function AccountPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-semibold">Account</h1>
      <p className="text-gray-600">{user?.email}</p>
    </div>
  );
}
