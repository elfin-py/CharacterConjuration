"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body>
        <main className="min-h-screen text-[color:var(--text)] flex items-center justify-center px-6">
          <div className="rounded-2xl cc-card cc-vignette p-8 max-w-xl w-full space-y-4 text-center">
            <p className="cc-ornament mx-auto">Fatal error</p>
            <h1 className="text-3xl cc-title">Rendering failed</h1>
            <p className="text-sm cc-ink">
              {error.message || "A fatal rendering error occurred."}
            </p>
            <button
              type="button"
              onClick={reset}
              className="pixel-btn rounded-lg bg-[color:var(--surface-2)] border border-[color:var(--border)] px-4 py-2 hover:bg-[color:var(--surface)] transition"
            >
              Retry
            </button>
          </div>
        </main>
      </body>
    </html>
  );
}
