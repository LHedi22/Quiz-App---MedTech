import { execFileSync } from "child_process";
import { existsSync } from "fs";
import path from "path";

const BACKEND_DIR = path.resolve(__dirname, "..", "..", "backend");
const VENV_PYTHON = path.join(
  BACKEND_DIR,
  ".venv",
  process.platform === "win32" ? "Scripts" : "bin",
  process.platform === "win32" ? "python.exe" : "python",
);
// CI installs backend deps into the runner's system/user Python rather than a
// project-local .venv (no such directory exists there) - fall back to
// PATH's python3/python in that case rather than assuming a venv always
// exists, which only held on this dev machine's own local setup.
const PYTHON = existsSync(VENV_PYTHON)
  ? VENV_PYTHON
  : process.env.PYTHON_BIN || (process.platform === "win32" ? "python" : "python3");
const SCRIPT = path.join(BACKEND_DIR, "scripts", "e2e_web_regression_scan.py");

/** Shells out to backend/scripts/e2e_web_regression_scan.py to drive the
 * scan step from a rendered PDF (these regression specs predate the Phase
 * 7c in-browser /scan screen and still exercise scanning at the API level).
 * See that script's own docstring for details. */
function run(args: string[]): Record<string, unknown> {
  const output = execFileSync(PYTHON, [SCRIPT, ...args], {
    cwd: BACKEND_DIR,
    encoding: "utf-8",
  });
  return JSON.parse(output.trim().split("\n").pop()!);
}

export interface SeededQuiz {
  email: string;
  password: string;
  token: string;
  quiz_id: string;
  version_id: string;
}

export function seedQuiz(title: string): SeededQuiz {
  return run(["seed-quiz", title]) as unknown as SeededQuiz;
}

export interface ScanResult {
  submission_id: string;
  status: string;
  total_score: number | null;
  flagged_question_numbers: number[];
  correct_option_for_flagged_row: string | null;
}

export function scanVersion(
  versionId: string,
  mode: string,
  token: string,
  studentId?: string,
): ScanResult {
  const args = ["scan", versionId, mode, token];
  if (studentId) args.push(studentId);
  return run(args) as unknown as ScanResult;
}

/** Scans using a signed PDF URL already obtained through the real Next.js
 * UI, rather than re-fetching it via the API - see pythonRegression's
 * `scan-url` command. */
export interface QrUnreadableResult {
  status_code: number;
  body: unknown;
}

export function scanVersionQrUnreadable(
  versionId: string,
  token: string,
  studentId?: string,
): QrUnreadableResult {
  const args = ["scan", versionId, "qr-unreadable", token];
  if (studentId) args.push(studentId);
  return run(args) as unknown as QrUnreadableResult;
}

export function scanVersionFromUrl(
  versionId: string,
  pdfUrl: string,
  mode: string,
  token: string,
  studentId?: string,
): ScanResult {
  const args = ["scan-url", versionId, pdfUrl, mode, token];
  if (studentId) args.push(studentId);
  return run(args) as unknown as ScanResult;
}

/** Mints an access token for an account created through the real signup UI,
 * so the token-gated POST /scan step can authenticate (web-app audit A2). */
export function tokenFor(email: string, password: string): string {
  return (run(["token", email, password]) as { token: string }).token;
}
