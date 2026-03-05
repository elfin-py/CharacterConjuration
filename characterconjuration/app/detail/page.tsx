\"use client\";

import { useEffect, useState } from \"react\";
import { useRouter, useSearchParams } from \"next/navigation\";

type CalcBreakdown = Record<string, any>;

export default function DetailPage() {
  const router = useRouter();
  const params = useSearchParams();
  const [data, setData] = useState<any | null>(null);

  useEffect(() => {
    const raw = window.localStorage.getItem(\"cc-latest-result\");
    if (!raw) {
      setData(null);
      return;
    }
    try {
      setData(JSON.parse(raw));
    } catch {
      setData(null);
    }
  }, []);

  const sheet = data?.sheet_json || data?.parsed;
  const calc: CalcBreakdown | null = data?.calc_breakdown || sheet?.calc_breakdown || null;

  if (!sheet) {
    return (
      <main className=\"min-h-screen bg-[#0b0b13] text-slate-100\">
        <div className=\"max-w-5xl mx-auto px-6 py-10\">
          <p className=\"text-slate-300\">No recent conjuration found. Generate a character first.</p>
          <button
            className=\"mt-4 pixel-btn rounded-lg bg-amber-300 text-[#111] px-4 py-2\"
            onClick={() => router.push(\"/\")}
          >
            Back to builder
          </button>
        </div>
      </main>
    );
  }

  const hover = (label: string, value: any, tip?: string) => (
    <div className=\"group relative\">
      <span className=\"font-semibold\">{label}:</span> <span>{value ?? \"—\"}</span>
      {tip && (
        <div className=\"pointer-events-none absolute left-0 top-full z-10 mt-2 w-72 rounded border border-amber-400/40 bg-[#11111b] p-2 text-xs text-amber-100 opacity-0 transition group-hover:opacity-100\">
          {tip}
        </div>
      )}
    </div>
  );

  return (
    <main className=\"min-h-screen bg-[#0b0b13] text-slate-100\">
      <div className=\"max-w-5xl mx-auto px-6 py-10 space-y-6\">
        <div className=\"flex items-center justify-between\">
          <div>
            <p className=\"text-xs uppercase tracking-[0.3em] text-amber-300\">Your conjuration</p>
            <h1 className=\"text-3xl font-semibold\">{params.get(\"type\") ?? \"character\"}</h1>
          </div>
          <button
            className=\"pixel-btn rounded-lg bg-[#1c1c2f] border border-[#35355a] px-3 py-2\"
            onClick={() => router.push(\"/\")}
          >
            Back
          </button>
        </div>

        <section className=\"rounded-2xl border border-[#35355a] bg-[#11111b]/80 p-6 space-y-3 pixel-border\">
          <h2 className=\"text-lg font-semibold\">Basics</h2>
          <div className=\"grid gap-2 text-sm md:grid-cols-2\">
            {hover(\"Name\", sheet.name)}
            {hover(\"Race\", sheet.race)}
            {hover(\"Class/Subclass\", `${sheet.class ?? \"\"} (${sheet.subclass ?? \"\"})`)}
            {hover(\"Level\", sheet.level)}
            {hover(\"Background\", sheet.background)}
            {hover(\"Alignment\", sheet.alignment)}
            {hover(\"Gender\", sheet.gender)}
            {hover(\"Age group\", sheet.age_group)}
            {hover(
              \"HP\",
              sheet.hitPoints,
              calc?.hp?.formula ? `HP = ${calc.hp.formula} = ${calc.hp.result}` : undefined,
            )}
            {hover(
              \"AC\",
              sheet.armorClass,
              calc?.ac?.formula ? `AC = ${calc.ac.formula} = ${calc.ac.result}` : undefined,
            )}
            {hover(\"Speed\", `${sheet.speed ?? \"—\"} ft`)}
            {hover(
              \"Proficiency Bonus\",
              calc?.proficiency_bonus?.result ?? \"—\",
              calc?.proficiency_bonus?.formula,
            )}
          </div>
        </section>

        <section className=\"rounded-2xl border border-[#35355a] bg-[#11111b]/80 p-6 space-y-3 pixel-border\">
          <h2 className=\"text-lg font-semibold\">Abilities</h2>
          <div className=\"grid grid-cols-3 gap-2 text-sm\">
            {Object.entries(sheet.abilities || {}).map(([k, v]) => (
              <div key={k} className=\"rounded border border-[#35355a] bg-[#0f0f1a] p-2\">
                <p className=\"text-xs uppercase text-slate-400\">{k.toUpperCase()}</p>
                <p className=\"text-lg font-semibold\">{v}</p>
              </div>
            ))}
          </div>
        </section>

        {calc?.spellcasting && (
          <section className=\"rounded-2xl border border-[#35355a] bg-[#11111b]/80 p-6 space-y-2 pixel-border\">
            <h2 className=\"text-lg font-semibold\">Spellcasting</h2>
            <div className=\"text-sm space-y-1\">
              {hover(\"Ability\", calc.spellcasting.ability)}
              {hover(\"Spell Save DC\", calc.spellcasting.spell_save_dc, calc.spellcasting.formula)}
              {hover(\"Spell Attack Bonus\", calc.spellcasting.spell_attack_bonus, calc.spellcasting.formula)}
              {calc?.spells &&
                hover(
                  \"Spell counts\",
                  `Max L${calc.spells.max_spell_level}`,
                  `Cantrips ${calc.spells.cantrips_expected}, Known ${calc.spells.spells_known_expected}, Prepared ${calc.spells.spells_prepared_expected}`,
                )}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
