"use client";

import { use, useEffect, useState } from "react";
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
  const [count, setCount] = useState(3);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function fetchVersionsAndPdfUrls() {
    const token = await getAccessToken();
    const loaded = await listQuizVersions(quizId, token);

    const urls: Record<string, string> = {};
    await Promise.all(
      loaded.map(async (version) => {
        const { url } = await getVersionPdfUrl(version.id, token);
        urls[version.id] = url;
      }),
    );
    return { loaded, urls };
  }

  async function loadVersions() {
    const { loaded, urls } = await fetchVersionsAndPdfUrls();
    setVersions(loaded);
    setPdfUrls(urls);
  }

  useEffect(() => {
    let ignore = false;
    fetchVersionsAndPdfUrls()
      .then(({ loaded, urls }) => {
        if (ignore) return;
        setVersions(loaded);
        setPdfUrls(urls);
      })
      .catch(() => {
        if (!ignore) setError("Could not load versions.");
      });
    return () => {
      ignore = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quizId]);

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const token = await getAccessToken();
      await createVersions(quizId, count, token);
      await loadVersions();
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
