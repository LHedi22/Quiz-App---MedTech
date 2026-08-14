import type { ReactNode } from "react";

const tones = {
  error: "border-flag/40 bg-flag-soft text-flag",
  success: "border-olive/30 bg-sand/50 text-olive-deep",
};

/** role="alert" preserved for error tone specifically - e2e specs and
 * screen readers both key off it for form-submission failures. */
export function Alert({
  tone,
  children,
  testId,
}: {
  tone: "error" | "success";
  children: ReactNode;
  testId?: string;
}) {
  return (
    <div
      role={tone === "error" ? "alert" : undefined}
      data-testid={testId}
      className={`rounded-sm border p-3 text-sm ${tones[tone]}`}
    >
      {children}
    </div>
  );
}
