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

  const isEnemy = (data?.entity_type || "").toLowerCase() === "enemy";

  if (!data) {
    return (
      <main className="min-h-screen bg-[#0b0b13] text-slate-50 flex items-center justify-center">
        <div className="rounded-xl border border-[#35355a] bg-[#11111b]/80 px-6 py-5 space-y-3">
          <p className="text-sm">No conjuration found. Generate one first.</p>
          <Link href="/" className="underline text-amber-300">
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
    <main className="min-h-screen bg-[#0b0b13] text-slate-50">
      <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-amber-300">Your conjuration</p>
            <h1 className="text-3xl font-semibold capitalize">{data.entity_type || "character"}</h1>
          </div>
          <div className="flex gap-2 text-sm">
            {isEnemy ? (
              <button
                className="pixel-btn rounded-lg bg-amber-300 text-[#111] px-3 py-2 font-semibold hover:bg-amber-200 transition"
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
            ) : (
              <button
                className="pixel-btn rounded-lg bg-amber-300 text-[#111] px-3 py-2 font-semibold hover:bg-amber-200 transition"
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
              className="pixel-btn rounded-lg bg-[#1c1c2f] border border-[#35355a] px-3 py-2 hover:bg-[#25253a] transition"
            >
              Back
            </Link>
          </div>
        </div>

        <div className="rounded-2xl border border-[#35355a] bg-[#11111b]/80 p-4 space-y-3 text-sm pixel-border">
          {isEnemy && data.stat_block && (
            <div className="space-y-1">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Stat block</p>
              <pre className="whitespace-pre-wrap text-xs bg-[#0c0c14] border border-[#35355a] p-3 rounded">
                {data.stat_block}
              </pre>
            </div>
          )}

          {parsed?.notes || parsed?.short_blurb ? (
            <div className="space-y-1">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Flavour</p>
              <p className="text-slate-200">{parsed.notes || parsed.short_blurb}</p>
            </div>
          ) : null}

          {parsed && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
              <div className="space-y-1">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Basics</p>
                <ul className="space-y-1 text-slate-200">
                  <li><strong>Name:</strong> {parsed.name || "—"}</li>
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
              <div className="space-y-1">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Abilities</p>
                <div className="grid grid-cols-3 gap-2">
                  {["STR", "DEX", "CON", "INT", "WIS", "CHA"].map((k) => (
                    <div key={k} className="rounded border border-[#35355a] bg-[#0c0c14]/60 px-2 py-1 text-center">
                      <p className="text-xs text-slate-400">{k}</p>
                      <p className="text-base font-semibold">{stats?.[k] ?? stats?.[k.toLowerCase()] ?? "—"}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
