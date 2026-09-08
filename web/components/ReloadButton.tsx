"use client";

import { Button } from "@/components/Button";

/** A "Try again" button usable from a server component's inline error state
 * (server components can't wire an onClick themselves). Full reload rather
 * than a router refresh so a transient backend failure is genuinely
 * re-attempted from scratch. */
export function ReloadButton({ label = "Try again" }: { label?: string }) {
  return (
    <Button type="button" variant="secondary" onClick={() => window.location.reload()}>
      {label}
    </Button>
  );
}
