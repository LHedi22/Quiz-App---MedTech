import type { LabelHTMLAttributes, SelectHTMLAttributes } from "react";

export function Select({
  label,
  id,
  labelProps,
  wrapperClassName = "space-y-1",
  className = "",
  children,
  ...selectProps
}: {
  label: string;
  id: string;
  labelProps?: LabelHTMLAttributes<HTMLLabelElement>;
  wrapperClassName?: string;
} & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className={wrapperClassName}>
      <label htmlFor={id} className="block text-sm font-medium text-ink" {...labelProps}>
        {label}
      </label>
      <select
        id={id}
        className={`rounded-sm border border-sand bg-paper-raised px-3 py-2 text-sm text-ink focus:border-olive focus:outline-none ${className}`}
        {...selectProps}
      >
        {children}
      </select>
    </div>
  );
}
