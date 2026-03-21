"use client";

import { useEffect, useState } from "react";
import NavBar from "../components/NavBar";
import Footer from "../components/Footer";

type MetricSummary = {
  mean: number | null;
  min: number | null;
  max: number | null;
  n: number;
};

type EvalPayload = {
  run_id?: string;
  summary?: any;
  condition_summary?: any;
  ragas_summary?: {
    status?: string;
    error?: string;
    overall?: Record<string, MetricSummary>;
    by_condition?: Record<string, Record<string, MetricSummary>>;
    notes?: string[];
  } | null;
};

export default function EvalPage() {
  const [data, setData] = useState<EvalPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/eval/latest", { cache: "no-store" });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(json?.detail || "Failed to load evaluation results");
      }
      setData(json);
    } catch (err: any) {
      setError(err?.message || "Failed to load evaluation results");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const runRagas = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await fetch("/api/eval/run-ragas", { method: "POST" });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(json?.detail?.error || json?.detail?.message || json?.detail || "RAGAS run failed");
      }
      await load();
    } catch (err: any) {
      setError(err?.message || "RAGAS run failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <main className="min-h-screen text-[color:var(--text)] flex flex-col">
      <NavBar />
      <div className="max-w-6xl mx-auto px-6 py-8 space-y-6 flex-1 w-full">
        <section className="rounded-2xl cc-card cc-vignette p-6 space-y-4">
          <p className="cc-ornament">Evaluation</p>
          <h1 className="text-3xl md:text-4xl font-semibold cc-title">RAG benchmark and RAGAS review</h1>
          <p className="text-sm cc-ink max-w-3xl">
            This page exposes the latest dissertation benchmark run, the manual comparative summaries, and an optional
            RAGAS pass over the same artifacts. Use the RAGAS results as retrieval diagnostics, not as a replacement for
            the project&apos;s rules-fit checks.
          </p>
          <div className="flex gap-2 flex-wrap">
            <button
              type="button"
              onClick={load}
              className="pixel-btn rounded-lg bg-[color:var(--surface-2)] border border-[color:var(--border)] px-3 py-2 hover:bg-[color:var(--surface)] transition"
            >
              Refresh
            </button>
            <button
              type="button"
              onClick={runRagas}
              disabled={running}
              className="pixel-btn rounded-lg bg-[color:var(--surface-2)] border border-[color:var(--border)] px-3 py-2 hover:bg-[color:var(--surface)] transition disabled:opacity-60"
            >
              {running ? "Running RAGAS..." : "Run RAGAS on latest benchmark"}
            </button>
          </div>
          {error ? <p className="text-sm text-red-700">{error}</p> : null}
        </section>

        {loading ? (
          <section className="rounded-2xl cc-card cc-vignette p-6">
            <p className="text-sm cc-ink">Loading evaluation artifacts...</p>
          </section>
        ) : data ? (
          <>
            <section className="rounded-2xl cc-card cc-vignette p-6 space-y-4">
              <h2 className="text-2xl font-semibold cc-title">Latest run</h2>
              <p className="text-sm cc-ink">Run id: {data.run_id || "—"}</p>
              <pre className="cc-card cc-paper rounded-lg p-3 text-xs whitespace-pre-wrap overflow-x-auto">
                {JSON.stringify(data.summary || {}, null, 2)}
              </pre>
            </section>

            <section className="rounded-2xl cc-card cc-vignette p-6 space-y-4">
              <h2 className="text-2xl font-semibold cc-title">Manual comparative summary</h2>
              <pre className="cc-card cc-paper rounded-lg p-3 text-xs whitespace-pre-wrap overflow-x-auto">
                {JSON.stringify(data.condition_summary || {}, null, 2)}
              </pre>
            </section>

            <section className="rounded-2xl cc-card cc-vignette p-6 space-y-4">
              <h2 className="text-2xl font-semibold cc-title">RAGAS summary</h2>
              {data.ragas_summary ? (
                <>
                  <p className="text-sm cc-ink">Status: {data.ragas_summary.status || "unknown"}</p>
                  {data.ragas_summary.error ? <p className="text-sm text-red-700">{data.ragas_summary.error}</p> : null}
                  {data.ragas_summary.notes?.length ? (
                    <ul className="list-disc pl-5 text-sm cc-ink space-y-1">
                      {data.ragas_summary.notes.map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  ) : null}
                  <pre className="cc-card cc-paper rounded-lg p-3 text-xs whitespace-pre-wrap overflow-x-auto">
                    {JSON.stringify(data.ragas_summary, null, 2)}
                  </pre>
                </>
              ) : (
                <p className="text-sm cc-ink">No RAGAS summary exists for the latest run yet.</p>
              )}
            </section>
          </>
        ) : null}
      </div>
      <Footer />
    </main>
  );
}
