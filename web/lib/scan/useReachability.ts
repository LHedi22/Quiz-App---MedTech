"use client";

import { useEffect, useState } from "react";

/** Tracks whether the backend is actually reachable, not just
 * `navigator.onLine` (which only reflects a network interface being up,
 * not the backend being reachable) - Subtask 7c.3 requires gating capture
 * on both. Pings `${pingUrl}` on mount, on the browser's `online` event,
 * and on an interval; goes offline immediately on the `offline` event
 * without waiting for the next ping. */
export function useReachability(pingUrl: string, intervalMs = 10000): boolean {
  // Always start `true` so the server render and the first client render
  // agree (no hydration mismatch if the page first loads while offline);
  // the mount effect's `ping()` corrects it immediately.
  const [online, setOnline] = useState(true);

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
        const response = await fetch(pingUrl, { signal: controller.signal, cache: "no-store" });
        clearTimeout(timeout);
        // A reachable-but-erroring backend (500/502/503, cold-start failure)
        // is not "online" for scanning - capture would just fail into the
        // "not submitted" state. A 4xx still counts as online (the backend
        // answered); the health route returns 200 anyway.
        if (!cancelled) setOnline(response.status < 500);
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
