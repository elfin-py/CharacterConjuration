"use client";

import { useEffect, useState } from "react";

export default function NavBar() {
  const [theme, setTheme] = useState<"light" | "dark">("dark");

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

  return (
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
  );
}
