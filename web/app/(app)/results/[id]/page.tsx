"use client";

import { use, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { listQuizSubmissions } from "@/lib/api/client";
import { getAccessToken } from "@/lib/supabase/client";
import type { SubmissionStatus, SubmissionSummary } from "@/lib/api/types";
import { Select } from "@/components/Select";
import { Button } from "@/components/Button";
import { Alert } from "@/components/Alert";
import { StatusBadge } from "@/components/StatusBadge";

type StatusFilter = "all" | SubmissionStatus;
type SortKey = "created_at" | "status";

export default function ResultsDashboardPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: quizId } = use(params);

  const [submissions, setSubmissions] = useState<SubmissionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    let ignore = false;
    (async () => {
      const token = await getAccessToken();
      const loaded = await listQuizSubmissions(quizId, token);
      if (!ignore) setSubmissions(loaded);
    })().catch(() => {
      setError("Could not load results.");
    });
    return () => {
      ignore = true;
    };
  }, [quizId]);

  const visible = useMemo(() => {
    if (!submissions) return [];
    const filtered =
      statusFilter === "all" ? submissions : submissions.filter((s) => s.status === statusFilter);
    const sorted = [...filtered].sort((a, b) => {
      const cmp =
        sortKey === "status"
          ? a.status.localeCompare(b.status)
          : a.created_at.localeCompare(b.created_at);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [submissions, statusFilter, sortKey, sortDir]);

  return (
    <div className="space-y-6">
      <h1 className="font-display text-2xl font-semibold text-olive-deep">Results</h1>

      {error && <Alert tone="error">{error}</Alert>}

      <div className="flex flex-wrap items-end gap-4">
        <Select
          label="Status"
          id="status-filter"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
        >
          <option value="all">All</option>
          <option value="finalized">Finalized</option>
          <option value="needs_review">Needs review</option>
          <option value="pending">Pending</option>
        </Select>
        <Select
          label="Sort by"
          id="sort-key"
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
        >
          <option value="created_at">Submitted</option>
          <option value="status">Status</option>
        </Select>
        <Button
          type="button"
          variant="secondary"
          onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
        >
          {sortDir === "asc" ? "Ascending" : "Descending"}
        </Button>
      </div>

      {submissions === null ? (
        <p className="text-ink-soft">Loading…</p>
      ) : visible.length === 0 ? (
        <p className="text-ink-soft" data-testid="empty-state">
          No submissions match this filter.
        </p>
      ) : (
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-sand text-ink-soft">
              <th className="py-2 pr-4 font-medium">Student</th>
              <th className="py-2 pr-4 font-medium">Score</th>
              <th className="py-2 pr-4 font-medium">Status</th>
              <th className="py-2 pr-4 font-medium">Submitted</th>
              <th className="py-2 pr-4"></th>
            </tr>
          </thead>
          <tbody data-testid="submissions-table-body">
            {visible.map((submission) => (
              <tr
                key={submission.id}
                className="border-b border-sand/60"
                data-testid="submission-row"
                data-status={submission.status}
              >
                <td className="py-2 pr-4">{submission.student_id ?? "—"}</td>
                <td className="py-2 pr-4 font-mono">
                  {submission.total_score !== null ? submission.total_score : "—"}
                </td>
                <td className="py-2 pr-4">
                  <StatusBadge status={submission.status} />
                </td>
                <td className="py-2 pr-4 text-ink-soft">
                  {new Date(submission.created_at).toLocaleString()}
                </td>
                <td className="py-2 pr-4">
                  <Link
                    href={`/submissions/${submission.id}`}
                    className="text-olive underline underline-offset-2"
                  >
                    {submission.status === "needs_review" ? "Review" : "View"}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
