"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type DetailData = {
  question?: string;
  answer?: string;
  entity_type?: string;
  parsed?: any;
  sheet_json?: any;
  stat_block?: string;
};

export default function DetailPage() {
  const [data, setData] = useState<DetailData | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">("dark");

  useEffect(() => {
    const stored = typeof window !== "undefined" ? window.localStorage.getItem("cc-latest-result") : null;
    if (stored) {
      try {
        setData(JSON.parse(stored));
      } catch {
        setData(null);
      }
    }
  }, []);

  useEffect(() => {
    const stored = typeof window !== "undefined" ? window.localStorage.getItem("cc-theme") : null;
    if (stored === "light" || stored === "dark") {
      setTheme(stored);
      document.documentElement.setAttribute("data-theme", stored);
    } else {
      const prefersDark =
        typeof window !== "undefined" &&
        window.matchMedia &&
        window.matchMedia("(prefers-color-scheme: dark)").matches;
      const initial = prefersDark ? "dark" : "light";
      setTheme(initial);
      document.documentElement.setAttribute("data-theme", initial);
    }
  }, []);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("cc-theme", next);
    }
    document.documentElement.setAttribute("data-theme", next);
  };

  const entityType = (data?.entity_type || "").toLowerCase();
  const isEnemy = entityType === "enemy";
  const isNpc = entityType === "npc";

  if (!data) {
    return (
      <main className="min-h-screen text-[color:var(--text)] flex items-center justify-center">
        <div className="rounded-2xl cc-card cc-vignette px-6 py-5 space-y-3">
          <p className="text-sm cc-ink">No conjuration found. Generate one first.</p>
          <Link href="/" className="underline text-[color:var(--accent)]">
            Back to builder
          </Link>
        </div>
      </main>
    );
  }

  const parsed = data?.parsed || {};
  const stats = parsed.stats || parsed.abilities || {};
  const hp = parsed.hp ?? parsed.hitPoints ?? "—";
  const ac = parsed.ac ?? parsed.armorClass ?? "—";
  const speed = parsed.speed ?? "—";

  return (
    <main className="min-h-screen text-[color:var(--text)]">
      <header className="sticky top-0 z-20 cc-header cc-paper backdrop-blur px-6 py-4 w-full">
        <div className="flex items-center justify-between max-w-6xl mx-auto">
          <div className="flex items-center gap-3">
            <img
              src="/logo-text.png"
              alt="Character Conjuration"
              className="h-10 w-auto max-w-[240px] object-contain"
            />
          </div>
          <div className="flex items-center gap-2 text-sm">
            <button
              type="button"
              onClick={toggleTheme}
              className="pixel-btn rounded-lg bg-[color:var(--surface-2)] border border-[color:var(--border)] px-3 py-1.5 hover:bg-[color:var(--surface)] transition"
              aria-label="Toggle theme"
            >
              <i className={`fa ${theme === "dark" ? "fa-moon-o" : "fa-sun-o"}`} aria-hidden="true" />
            </button>
            <button className="pixel-btn rounded-lg bg-[color:var(--surface-2)] border border-[color:var(--border)] px-3 py-1.5 hover:bg-[color:var(--surface)] transition">
              Sign in
            </button>
            <button className="pixel-btn rounded-lg bg-[color:var(--surface-2)] border border-[color:var(--border)] px-3 py-1.5 hover:bg-[color:var(--surface)] transition">
              Log in
            </button>
          </div>
        </div>
      </header>
      <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        <section className="rounded-2xl cc-card cc-vignette p-6 space-y-4">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div className="space-y-2">
              <p className="cc-ornament">Your conjuration</p>
              <h1 className="text-3xl md:text-4xl font-semibold capitalize cc-title">
                {data.entity_type || "character"}
              </h1>
              <p className="text-sm cc-ink">
                Review the generated details below. Download the sheet or stat block if you need a printable copy.
              </p>
            </div>
            <div className="flex gap-2 text-sm flex-wrap">
            {isEnemy ? (
              <button
                className="pixel-btn rounded-lg cc-paper border border-[color:var(--border)] px-3 py-2 font-semibold hover:brightness-110 transition"
                disabled={!data.sheet_json}
                onClick={async () => {
                  if (!data.sheet_json) return;
                  try {
                    const res = await fetch("/api/fill_statblock", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ sheet_json: data.sheet_json }),
                    });
                    if (!res.ok) {
                      alert("Failed to build stat block");
                      return;
                    }
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `${data.sheet_json?.name || "enemy"}_stat_block.pdf`;
                    a.click();
                    URL.revokeObjectURL(url);
                  } catch (err) {
                    console.error(err);
                    alert("Error building stat block");
                  }
                }}
              >
                Download stat block
              </button>
            ) : isNpc ? null : (
              <button
                className="pixel-btn rounded-lg cc-paper border border-[color:var(--border)] px-3 py-2 font-semibold hover:brightness-110 transition"
                disabled={!data.sheet_json}
                onClick={async () => {
                  if (!data.sheet_json) return;
                  try {
                    const res = await fetch("/api/fill_sheet", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ sheet_json: data.sheet_json }),
                    });
                    if (!res.ok) {
                      alert("Failed to build PDF");
                      return;
                    }
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `${data.sheet_json?.name || "character"}_sheet.pdf`;
                    a.click();
                    URL.revokeObjectURL(url);
                  } catch (err) {
                    console.error(err);
                    alert("Error building PDF");
                  }
                }}
              >
                Download filled 5e sheet
              </button>
            )}
            <Link
              href="/"
              className="pixel-btn rounded-lg cc-paper border border-[color:var(--border)] px-3 py-2 hover:brightness-110 transition"
            >
              Back
            </Link>
          </div>
          </div>
        </section>

        <div className="rounded-2xl cc-card cc-vignette p-4 space-y-3 text-sm">
          {isEnemy && data.stat_block && (
            <div className="space-y-1">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text)]/60">Stat block</p>
              <pre className="whitespace-pre-wrap text-xs cc-card cc-paper p-3 rounded">
                {data.stat_block}
              </pre>
            </div>
          )}

          {parsed?.notes || parsed?.short_blurb ? (
            <div className="space-y-1">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text)]/60">Flavour</p>
              <p className="cc-ink">{parsed.notes || parsed.short_blurb}</p>
            </div>
          ) : null}

          {parsed && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
              <div className="space-y-1">
                <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text)]/60">Basics</p>
                <ul className="space-y-1 cc-ink">
                  <li><strong>Name:</strong> {parsed.name || "—"}</li>
                  <li><strong>Size:</strong> {parsed.size || "—"}</li>
                  <li><strong>Race:</strong> {parsed.race || "—"}</li>
                  <li><strong>Class/Subclass:</strong> {parsed.class || "—"} {parsed.subclass ? `(${parsed.subclass})` : ""}</li>
                  <li><strong>Level:</strong> {parsed.level ?? "—"}</li>
                  <li><strong>Background:</strong> {parsed.background || "—"}</li>
                  <li><strong>Alignment:</strong> {parsed.alignment || "—"}</li>
                  <li><strong>Gender:</strong> {parsed.gender || "—"}</li>
                  <li><strong>Age group:</strong> {parsed.age_group || "—"}</li>
                  <li><strong>HP / AC / Speed:</strong> {hp} / {ac} / {speed} ft</li>
                </ul>
              </div>
              {!isNpc && (
                <div className="space-y-1">
                  <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text)]/60">Abilities</p>
                  <div className="grid grid-cols-3 gap-2">
                    {["STR", "DEX", "CON", "INT", "WIS", "CHA"].map((k) => (
                      <div key={k} className="rounded cc-card cc-paper px-2 py-1 text-center">
                        <p className="text-xs text-[color:var(--text)]/60">{k}</p>
                        <p className="text-base font-semibold cc-ink">
                          {stats?.[k] ?? stats?.[k.toLowerCase()] ?? "—"}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <footer className="cc-footer p-6 text-sm cc-ink w-full">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between max-w-6xl mx-auto">
          <div className="space-y-2">
            <p className="cc-title text-base font-bold">Character Conjuration</p>
            <p className="text-sm">
              A final year undergraduate synoptic project by Poppy Edwards.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
            <a className="underline" href="https://github.com/elfin-py/CharacterConjuration" target="_blank" rel="noreferrer">
              GitHub repository
            </a>
            <a className="underline" href="https://github.com/elfin-py" target="_blank" rel="noreferrer">
              GitHub profile
            </a>
            <a className="underline" href="https://dnd.wizards.com/" target="_blank" rel="noreferrer">
              Dungeons &amp; Dragons official site
            </a>
            <a className="underline" href="https://gdpr.eu/" target="_blank" rel="noreferrer">
              GDPR overview
            </a>
            <a className="underline" href="https://gdpr.eu/what-is-gdpr/" target="_blank" rel="noreferrer">
              Data protection basics
            </a>
          </div>
        </div>
      </footer>
    </main>
  );
}
