import { AuthExpiredError } from "@/lib/authError";
import type {
  CreateVersionsResult,
  Quiz,
  RowError,
  SubmissionDetail,
  SubmissionStatus,
  SubmissionSummary,
  UploadResult,
  VersionPdfResult,
  VersionSummary,
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL!;

/** Every API call aborts after this long rather than hanging the awaiting
 * server component (and holding the Vercel/Cloud Run request open) until an
 * upstream timeout. */
const REQUEST_TIMEOUT_MS = 15000;

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`API request failed with status ${status}`);
  }
}

/** A request that never got a response within REQUEST_TIMEOUT_MS. Extends
 * ApiError (status 0, no body) so existing `catch (e) { if (e instanceof
 * ApiError) ... }` paths keep working. */
export class ApiTimeoutError extends ApiError {
  constructor(public path: string) {
    super(0, null);
    this.message = `API request to ${path} timed out after ${REQUEST_TIMEOUT_MS}ms`;
  }
}

/** Thrown specifically for a 422 upload response shaped like Phase 2's
 * `ParseError` (`{ detail: { errors: RowError[] } }`), so callers can
 * render per-row messages without re-parsing a generic ApiError body. */
export class UploadValidationError extends ApiError {
  constructor(
    status: number,
    body: unknown,
    public errors: RowError[],
  ) {
    super(status, body);
  }
}

function isRowErrorList(value: unknown): value is RowError[] {
  return (
    Array.isArray(value) &&
    value.every(
      (item) =>
        typeof item === "object" &&
        item !== null &&
        typeof (item as RowError).row_number === "number" &&
        Array.isArray((item as RowError).messages),
    )
  );
}

async function request<T>(
  path: string,
  accessToken: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      // A caller-supplied signal wins if there is one; otherwise every
      // request gets the default timeout.
      signal: init?.signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      headers: {
        Authorization: `Bearer ${accessToken}`,
        ...(init?.headers ?? {}),
      },
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "TimeoutError") {
      throw new ApiTimeoutError(path);
    }
    throw err;
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);

    // A 401 from the backend means the bearer token is invalid/expired -
    // surface it as an auth-expiry so the client redirects to /login rather
    // than rendering a generic failure.
    if (response.status === 401) {
      throw new AuthExpiredError();
    }

    const errors = (body as { detail?: { errors?: unknown } } | null)?.detail?.errors;
    if (response.status === 422 && isRowErrorList(errors)) {
      throw new UploadValidationError(response.status, body, errors);
    }

    throw new ApiError(response.status, body);
  }

  return response.json();
}

export function createQuiz(title: string, accessToken: string): Promise<Quiz> {
  return request<Quiz>("/quizzes", accessToken, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export function listQuizzes(accessToken: string): Promise<Quiz[]> {
  return request<Quiz[]>("/quizzes", accessToken);
}

export function uploadQuizExcel(
  quizId: string,
  file: File,
  accessToken: string,
): Promise<UploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  // No Content-Type header here - the browser sets the multipart boundary
  // automatically when the body is a FormData instance.
  return request<UploadResult>(`/quizzes/${quizId}/upload`, accessToken, {
    method: "POST",
    body: formData,
  });
}

export function createVersions(
  quizId: string,
  count: number,
  accessToken: string,
): Promise<CreateVersionsResult> {
  return request<CreateVersionsResult>(`/quizzes/${quizId}/versions`, accessToken, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ count }),
  });
}

export function listQuizVersions(
  quizId: string,
  accessToken: string,
): Promise<VersionSummary[]> {
  return request<VersionSummary[]>(`/quizzes/${quizId}/versions`, accessToken);
}

export function getVersionPdfUrl(
  versionId: string,
  accessToken: string,
): Promise<VersionPdfResult> {
  return request<VersionPdfResult>(`/versions/${versionId}/pdf`, accessToken);
}

export function listQuizSubmissions(
  quizId: string,
  accessToken: string,
  status?: SubmissionStatus,
): Promise<SubmissionSummary[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<SubmissionSummary[]>(`/quizzes/${quizId}/submissions${query}`, accessToken);
}

export function getSubmission(
  submissionId: string,
  accessToken: string,
): Promise<SubmissionDetail> {
  return request<SubmissionDetail>(`/submissions/${submissionId}`, accessToken);
}

/** Set the option the professor says the student marked on one answer.
 * `markedOption` is "A"|"B"|"C"|"D", or null for a blank/unanswered
 * question. Works on any answer of a submission the professor owns,
 * regardless of the submission's status or whether the answer was flagged. */
export function correctAnswer(
  submissionId: string,
  answerId: string,
  markedOption: string | null,
  accessToken: string,
): Promise<SubmissionDetail> {
  return request<SubmissionDetail>(
    `/submissions/${submissionId}/answers/${answerId}`,
    accessToken,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ marked_option: markedOption }),
    },
  );
}

export function correctName(
  submissionId: string,
  studentName: string,
  accessToken: string,
): Promise<SubmissionDetail> {
  return request<SubmissionDetail>(`/submissions/${submissionId}/name`, accessToken, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ student_name: studentName }),
  });
}
