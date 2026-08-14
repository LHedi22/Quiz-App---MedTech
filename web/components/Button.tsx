import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary";

const base =
  "inline-flex items-center justify-center rounded-sm px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-olive-deep";

const variants: Record<Variant, string> = {
  primary: "bg-olive text-paper hover:bg-olive-deep",
  secondary: "border border-olive text-olive hover:bg-sand",
};

export function Button({
  variant = "primary",
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return <button className={`${base} ${variants[variant]} ${className}`} {...rest} />;
}
