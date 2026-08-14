"use client";

import { useEffect, useState } from "react";

/** Tracks whether the backend is actually reachable, not just
 * `navigator.onLine` (which only reflects a network interface being up,
 * not the backend being reachable) - Subtask 7c.3 requires gating capture
 * on both. Pings `${pingUrl}` on mount, on the browser's `online` event,
 * and on an interval; goes offline immediately on the `offline` event
 * without waiting for the next ping. */
export function useReachability(pingUrl: string, intervalMs = 10000): boolean {
  const [online, setOnline] = useState<boolean>(() =>
    typeof navigator === "undefined" ? true : navigator.onLine,
  );

  useEffect(() => {
    let cancelled = false;

    async function ping() {
      if (!navigator.onLine) {
        if (!cancelled) setOnline(false);
        return;
      }
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 4000);
        await fetch(pingUrl, { signal: controller.signal, cache: "no-store" });
        clearTimeout(timeout);
        if (!cancelled) setOnline(true);
      } catch {
        if (!cancelled) setOnline(false);
      }
    }

    function handleOffline() {
      setOnline(false);
    }
    function handleOnline() {
      void ping();
    }

    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);
    void ping();
    const timer = setInterval(ping, intervalMs);

    return () => {
      cancelled = true;
      clearInterval(timer);
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
    };
  }, [pingUrl, intervalMs]);

  return online;
}
