import type { HTMLAttributes } from "react";

export function Card({ className = "", ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-sm border border-sand bg-paper-raised p-4 ${className}`}
      {...rest}
    />
  );
}
