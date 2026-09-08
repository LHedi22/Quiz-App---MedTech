"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { resolveSignupRedirect } from "./resolveRedirect";

export async function signup(formData: FormData) {
  const supabase = await createClient();

  const email = formData.get("email") as string;
  const password = formData.get("password") as string;

  const result = await supabase.auth.signUp({ email, password });

  redirect(resolveSignupRedirect(result));
}
