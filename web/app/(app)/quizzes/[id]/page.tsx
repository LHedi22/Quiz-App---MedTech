"use client";

import { use, useCallback, useEffect, useState } from "react";
import {
  createVersions,
  getVersionPdfUrl,
  listQuizVersions,
} from "@/lib/api/client";
import { getAccessToken } from "@/lib/supabase/client";
import type { VersionSummary } from "@/lib/api/types";
import { Field } from "@/components/Field";
import { Button } from "@/components/Button";
import { Alert } from "@/components/Alert";
import { Bubble } from "@/components/Bubble";

export default function QuizDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: quizId } = use(params);

  const [versions, setVersions] = useState<VersionSummary[] | null>(null);
  const [pdfUrls, setPdfUrls] = useState<Record<string, string>>({});
  // Versions whose signed-URL fetch failed - shown with a per-row retry
  // rather than failing the whole page (a storage hiccup on one version
  // must not hide the other versions or the list itself).
  const [pdfFailedIds, setPdfFailedIds] = useState<Record<string, boolean>>({});
  const [count, setCount] = useState(3);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadPdfUrl = useCallback(async (versionId: string, token: string) => {
    try {
      const { url } = await getVersionPdfUrl(versionId, token);
      setPdfUrls((prev) => ({ ...prev, [versionId]: url }));
      setPdfFailedIds((prev) => {
        if (!prev[versionId]) return prev;
        const next = { ...prev };
        delete next[versionId];
        return next;
      });
    } catch {
      setPdfFailedIds((prev) => ({ ...prev, [versionId]: true }));
    }
  }, []);

  const loadVersions = useCallback(async () => {
    const token = await getAccessToken();
    const loaded = await listQuizVersions(quizId, token);
    setVersions(loaded);
    // allSettled, not all: one rejected URL fetch must not throw here.
    await Promise.allSettled(loaded.map((version) => loadPdfUrl(version.id, token)));
  }, [quizId, loadPdfUrl]);

  useEffect(() => {
    let ignore = false;
    (async () => {
      const token = await getAccessToken();
      const loaded = await listQuizVersions(quizId, token);
      if (ignore) return;
      setVersions(loaded);
      await Promise.allSettled(loaded.map((version) => loadPdfUrl(version.id, token)));
    })().catch(() => {
      setError("Could not load versions.");
    });
    return () => {
      ignore = true;
    };
  }, [quizId, loadPdfUrl]);

  async function retryPdf(versionId: string) {
    const token = await getAccessToken();
    await loadPdfUrl(versionId, token);
  }

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const token = await getAccessToken();
      await createVersions(quizId, count, token);
      try {
        await loadVersions();
      } catch {
        // Generation succeeded server-side; only the refresh failed.
        setNotice("Versions generated. Refresh the page to see them.");
      }
    } catch {
      setError("Could not generate versions. Does this quiz have any questions?");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="font-display text-2xl font-semibold text-olive-deep">Versions</h1>

      {error && <Alert tone="error">{error}</Alert>}
      {notice && <Alert tone="success">{notice}</Alert>}

      {versions === null ? (
        <p className="text-ink-soft">Loading…</p>
      ) : versions.length === 0 ? (
        <form onSubmit={handleGenerate} className="space-y-4">
          <Field
            label="Number of versions"
            id="count"
            type="number"
            min={1}
            required
            value={count}
            onChange={(e) => setCount(Number(e.target.value))}
            className="w-32"
          />
          <Button type="submit" disabled={busy}>
            Generate versions
          </Button>
        </form>
      ) : (
        <ul className="divide-y divide-sand rounded-sm border border-sand bg-paper-raised">
          {versions.map((version) => (
            <li
              key={version.id}
              className="flex items-center justify-between px-4 py-3"
              data-version-id={version.id}
            >
              <span className="flex items-center gap-2">
                <Bubble tone="outline" />
                Version <span className="font-mono">{version.version_number}</span>
              </span>
              {pdfUrls[version.id] ? (
                <a
                  href={pdfUrls[version.id]}
                  target="_blank"
                  rel="noreferrer"
                  data-testid="download-pdf"
                  className="rounded-sm bg-olive px-3 py-1.5 text-sm font-medium text-paper hover:bg-olive-deep"
                >
                  Download PDF
                </a>
              ) : pdfFailedIds[version.id] ? (
                <button
                  type="button"
                  data-testid="retry-pdf"
                  onClick={() => retryPdf(version.id)}
                  className="rounded-sm border border-flag/40 px-3 py-1.5 text-sm font-medium text-flag hover:bg-flag-soft"
                >
                  PDF unavailable — retry
                </button>
              ) : (
                <span className="text-sm text-ink-soft">Preparing…</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
