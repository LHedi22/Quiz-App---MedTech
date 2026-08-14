import { Bubble } from "./Bubble";
import type { SubmissionStatus } from "@/lib/api/types";

const STATUS: Record<SubmissionStatus, { label: string; tone: "olive" | "flag" | "outline" }> = {
  finalized: { label: "Finalized", tone: "olive" },
  needs_review: { label: "Needs review", tone: "flag" },
  pending: { label: "Pending", tone: "outline" },
};

export function StatusBadge({ status }: { status: SubmissionStatus }) {
  const { label, tone } = STATUS[status];
  return (
    <span className="inline-flex items-center gap-2">
      <Bubble tone={tone} />
      {label}
    </span>
  );
}
