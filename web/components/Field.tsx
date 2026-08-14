import type { InputHTMLAttributes, LabelHTMLAttributes } from "react";

/** Label + input pair. Renders a <label htmlFor> associated with the
 * input's id, matching every e2e spec's getByLabel() lookups exactly -
 * the label text passed in must stay verbatim (tests key off it). */
export function Field({
  label,
  id,
  labelProps,
  className = "",
  ...inputProps
}: {
  label: string;
  id: string;
  labelProps?: LabelHTMLAttributes<HTMLLabelElement>;
} & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium text-ink" {...labelProps}>
        {label}
      </label>
      <input
        id={id}
        className={`rounded-sm border border-sand bg-paper-raised px-3 py-2 text-ink placeholder:text-ink-soft focus:border-olive focus:outline-none ${
          className || "w-full"
        }`}
        {...inputProps}
      />
    </div>
  );
}
