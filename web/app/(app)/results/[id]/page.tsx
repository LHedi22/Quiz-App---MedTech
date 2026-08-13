"use client";

import { use, useEffect, useMemo, useState } from "react";
import { listQuizSubmissions } from "@/lib/api/client";
import { getAccessToken } from "@/lib/supabase/client";
import type { SubmissionStatus, SubmissionSummary } from "@/lib/api/types";

type StatusFilter = "all" | SubmissionStatus;
type SortKey = "created_at" | "status";

const STATUS_LABELS: Record<SubmissionStatus, string> = {
  pending: "Pending",
  finalized: "Finalized",
  needs_review: "Needs review",
};

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
      <h1 className="text-2xl font-semibold">Results</h1>

      {error && (
        <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1">
          <label htmlFor="status-filter" className="block text-sm font-medium">
            Status
          </label>
          <select
            id="status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            className="rounded border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="all">All</option>
            <option value="finalized">Finalized</option>
            <option value="needs_review">Needs review</option>
            <option value="pending">Pending</option>
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="sort-key" className="block text-sm font-medium">
            Sort by
          </label>
          <select
            id="sort-key"
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            className="rounded border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="created_at">Submitted</option>
            <option value="status">Status</option>
          </select>
        </div>
        <button
          type="button"
          onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
          className="rounded border border-gray-300 px-3 py-2 text-sm"
        >
          {sortDir === "asc" ? "Ascending" : "Descending"}
        </button>
      </div>

      {submissions === null ? (
        <p className="text-gray-600">Loading…</p>
      ) : visible.length === 0 ? (
        <p className="text-gray-600" data-testid="empty-state">
          No submissions match this filter.
        </p>
      ) : (
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="py-2 pr-4">Student</th>
              <th className="py-2 pr-4">Score</th>
              <th className="py-2 pr-4">Status</th>
              <th className="py-2 pr-4">Submitted</th>
            </tr>
          </thead>
          <tbody data-testid="submissions-table-body">
            {visible.map((submission) => (
              <tr
                key={submission.id}
                className="border-b border-gray-100"
                data-testid="submission-row"
                data-status={submission.status}
              >
                <td className="py-2 pr-4">{submission.student_id ?? "—"}</td>
                <td className="py-2 pr-4">
                  {submission.total_score !== null ? submission.total_score : "—"}
                </td>
                <td className="py-2 pr-4">{STATUS_LABELS[submission.status]}</td>
                <td className="py-2 pr-4">
                  {new Date(submission.created_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
