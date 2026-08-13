import { redirect } from "next/navigation";

// Reachable only when authenticated - proxy.ts already redirects
// unauthenticated requests to /login before this renders.
export default function RootPage() {
  redirect("/quizzes");
}
