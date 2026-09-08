import type { NextConfig } from "next";

// Baseline HTTP security headers (web-app audit A4). The app shows student
// names and scores and had none of these - it was clickjackable and had no
// CSP. Applied to every route via `/:path*`.
//
// connect-src is built from the same public env vars the browser client
// already uses, so a deploy that sets those correctly gets a CSP that
// matches its real backends without hardcoding a domain here. The CSP is
// **report-only** for now: it surfaces violations without breaking HMR in
// dev or a mis-scoped rule in prod. Tightening it (dropping 'unsafe-eval',
// moving to nonces) is deliberate follow-up work, not part of this baseline.
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

const connectSrc = ["'self'", supabaseUrl, apiBaseUrl, "ws:", "wss:"]
  .filter(Boolean)
  .join(" ");

const contentSecurityPolicy = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src ${connectSrc}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
]
  .join("; ")
  .concat(";");

const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "same-origin" },
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
  {
    key: "Permissions-Policy",
    // camera=(self): the /scan screen needs getUserMedia. Everything else off.
    value: "camera=(self), microphone=(), geolocation=(), browsing-topics=()",
  },
  { key: "Content-Security-Policy-Report-Only", value: contentSecurityPolicy },
];

const nextConfig: NextConfig = {
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
