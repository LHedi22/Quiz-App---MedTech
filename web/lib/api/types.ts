// Hand-written TS types mirroring backend/app/models/*.py and the actual
// dict shapes the routers return (some routers return plain `dict`, not a
// Pydantic response_model, so these follow the router source directly).

export interface Quiz {
  id: string;
  title: string;
  created_at: string;
}

export interface RowError {
  row_number: number;
  messages: string[];
}

export interface UploadResult {
  quiz_id: string;
  questions_inserted: number;
}

export interface VersionSummary {
  id: string;
  version_number: number;
}

export interface CreateVersionsResult {
  quiz_id: string;
  versions_created: number;
}

export interface VersionPdfResult {
  url: string;
}

export type SubmissionStatus = "pending" | "finalized" | "needs_review";

export interface SubmissionSummary {
  id: string;
  version_id: string;
  student_id: string | null;
  student_name: string | null;
  name_confidence: number | null;
  name_flagged: boolean;
  name_manually_edited: boolean;
  total_score: number | null;
  status: SubmissionStatus;
  created_at: string;
}

export interface AnswerDetail {
  id: string;
  question_no: number;
  detected_option: string | null;
  confidence: number;
  flagged: boolean;
  correct: boolean | null;
  score: number | null;
  /** Canonical question text + master-key answer, joined server-side so the
   * review screen can show them next to what the student marked. Null only
   * if the answer row has no matching canonical question. */
  question_text: string | null;
  key_option: string | null;
  /** True once a professor has set this answer's marked option by hand. */
  manually_edited: boolean;
  edited_at: string | null;
}

export interface SubmissionDetail extends SubmissionSummary {
  answers: AnswerDetail[];
}
