import { execFileSync } from "child_process";
import path from "path";

const BACKEND_DIR = path.resolve(__dirname, "..", "..", "backend");
const PYTHON = path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe");
const SCRIPT = path.join(BACKEND_DIR, "scripts", "e2e_web_regression_scan.py");

/** Shells out to backend/scripts/e2e_web_regression_scan.py - the one step
 * in these regression tests with no web UI equivalent (scanning is
 * mobile-only). See that script's own docstring for why. */
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
  studentId?: string,
): ScanResult {
  const args = ["scan-url", versionId, pdfUrl, mode];
  if (studentId) args.push(studentId);
  return run(args) as unknown as ScanResult;
}
