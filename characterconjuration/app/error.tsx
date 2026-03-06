"use client";

type ErrorPageProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function ErrorPage({ error, reset }: ErrorPageProps) {
  return (
    <main className="min-h-screen text-[color:var(--text)] flex items-center justify-center px-6">
      <div className="rounded-2xl cc-card cc-vignette p-8 max-w-xl w-full space-y-4 text-center">
        <p className="cc-ornament mx-auto">Application error</p>
        <h1 className="text-3xl cc-title">Something went wrong</h1>
        <p className="text-sm cc-ink">
          {error.message || "An unexpected error interrupted rendering."}
        </p>
        <div className="flex items-center justify-center gap-3">
          <button
            type="button"
            onClick={reset}
            className="pixel-btn rounded-lg bg-[color:var(--surface-2)] border border-[color:var(--border)] px-4 py-2 hover:bg-[color:var(--surface)] transition"
          >
            Try again
          </button>
          <a
            href="/"
            className="pixel-btn rounded-lg bg-[color:var(--surface-2)] border border-[color:var(--border)] px-4 py-2 hover:bg-[color:var(--surface)] transition"
          >
            Back home
          </a>
        </div>
      </div>
    </main>
  );
}
