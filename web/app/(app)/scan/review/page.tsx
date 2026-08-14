"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { getSubmission } from "@/lib/api/client";
import { getAccessToken } from "@/lib/supabase/client";
import type { SubmissionDetail } from "@/lib/api/types";
import { Alert } from "@/components/Alert";
import { Bubble } from "@/components/Bubble";
import { StatusBadge } from "@/components/StatusBadge";

/** Filtered by an explicit id list from the query string rather than by
 * quiz - the scan capture screen (Subtask 7c.4) doesn't know which quiz(zes)
 * a session's scans belong to (`POST /scan`'s response has no quiz_id, see
 * backend/app/routers/scan.py), and a session can legitimately span more
 * than one quiz since the QR code alone determines the version. This is the
 * only view that shows *exactly* this session's needs_review submissions,
 * as opposed to the results dashboard's quiz-wide "needs_review" filter,
 * which would also show older unrelated submissions for the same quiz. */
function ScanReviewList() {
  const searchParams = useSearchParams();
  const ids = useMemo(
    () => (searchParams.get("ids") ?? "").split(",").filter(Boolean),
    [searchParams],
  );

  const [submissions, setSubmissions] = useState<SubmissionDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    (async () => {
      if (ids.length === 0) {
        if (!ignore) setSubmissions([]);
        return;
      }
      const token = await getAccessToken();
      const loaded = await Promise.all(ids.map((id) => getSubmission(id, token)));
      if (!ignore) setSubmissions(loaded);
    })().catch(() => {
      if (!ignore) setError("Could not load this session's flagged submissions.");
    });
    return () => {
      ignore = true;
    };
  }, [ids]);

  if (error) return <Alert tone="error">{error}</Alert>;
  if (submissions === null) return <p className="text-ink-soft">Loading…</p>;

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="font-display text-2xl font-semibold text-olive-deep">
        This session&apos;s flagged submissions
      </h1>

      {submissions.length === 0 ? (
        <p className="text-ink-soft" data-testid="empty-state">
          Nothing from this session needs review.
        </p>
      ) : (
        <ul className="divide-y divide-sand rounded-sm border border-sand bg-paper-raised" data-testid="scan-review-list">
          {submissions.map((submission) => (
            <li key={submission.id} data-testid="scan-review-item" data-submission-id={submission.id}>
              <Link
                href={`/submissions/${submission.id}`}
                className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-sand/40"
              >
                <span className="inline-flex items-center gap-2">
                  {submission.name_flagged && <Bubble tone="flag" size={7} />}
                  {submission.student_name ?? submission.student_id ?? "—"}
                </span>
                <StatusBadge status={submission.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function ScanReviewPage() {
  return (
    <Suspense fallback={<p className="text-ink-soft">Loading…</p>}>
      <ScanReviewList />
    </Suspense>
  );
}
