"use client";

import { use, useEffect, useState } from "react";
import {
  createVersions,
  getVersionPdfUrl,
  listQuizVersions,
} from "@/lib/api/client";
import { getAccessToken } from "@/lib/supabase/client";
import type { VersionSummary } from "@/lib/api/types";

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
      <h1 className="text-2xl font-semibold">Versions</h1>

      {error && (
        <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {versions === null ? (
        <p className="text-gray-600">Loading…</p>
      ) : versions.length === 0 ? (
        <form onSubmit={handleGenerate} className="space-y-4">
          <div className="space-y-1">
            <label htmlFor="count" className="block text-sm font-medium">
              Number of versions
            </label>
            <input
              id="count"
              type="number"
              min={1}
              required
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              className="w-32 rounded border border-gray-300 px-3 py-2"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-black px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            Generate versions
          </button>
        </form>
      ) : (
        <ul className="divide-y divide-gray-200 rounded border border-gray-200">
          {versions.map((version) => (
            <li
              key={version.id}
              className="flex items-center justify-between px-4 py-3"
              data-version-id={version.id}
            >
              <span>Version {version.version_number}</span>
              {pdfUrls[version.id] ? (
                <a
                  href={pdfUrls[version.id]}
                  target="_blank"
                  rel="noreferrer"
                  data-testid="download-pdf"
                  className="rounded bg-black px-3 py-1.5 text-sm text-white"
                >
                  Download PDF
                </a>
              ) : (
                <span className="text-sm text-gray-500">Preparing…</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
