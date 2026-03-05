"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type RollMode = "auto" | "standard_array" | "manual";
type BuilderType = "character" | "enemy" | "npc";

interface GenerateResponse {
  question?: string;
  answer?: string;
  error?: string;
  [key: string]: any;
}

const abilityKeys = ["STR", "DEX", "CON", "INT", "WIS", "CHA"] as const;
const raceOptions = [
  "",
  "Dragonborn",
  "Dwarf",
  "Elf",
  "Gnome",
  "Half-Elf",
  "Half-Orc",
  "Halfling",
  "Human",
  "Tiefling",
];
const classOptions = [
  "",
  "Barbarian",
  "Bard",
  "Cleric",
  "Druid",
  "Fighter",
  "Monk",
  "Paladin",
  "Ranger",
  "Rogue",
  "Sorcerer",
  "Warlock",
  "Wizard",
];
const alignmentOptions = [
  "",
  "Lawful Good",
  "Neutral Good",
  "Chaotic Good",
  "Lawful Neutral",
  "True Neutral",
  "Chaotic Neutral",
  "Lawful Evil",
  "Neutral Evil",
  "Chaotic Evil",
];

const builderOptions: {
  key: BuilderType;
  title: string;
  blurb: string;
}[] = [
  {
    key: "character",
    title: "Player Character",
    blurb: "Forge a hero with stats, race, class, and a quest hook.",
  },
  {
    key: "enemy",
    title: "Enemy / Monster",
    blurb: "Conjure a foe with a fast stat-style summary and tactics.",
  },
  {
    key: "npc",
    title: "NPC",
    blurb: "Draft a memorable quest-giver, rival, or ally with flavor.",
  },
];

const loadingPhrases = [
  "Camouflaging mimics",
  "Reading action economy",
  "Preparing spells",
  "Fireballing in a 5x5 room",
  "Sharpening daggers",
  "Rolling stealth checks",
  "Counting rations",
  "Arguing about initiative",
  "Negotiating with goblins",
  "Polishing a lucky d20",
  "Mapping the dungeon",
  "Consulting the sage",
];

export default function HomePage() {
  const router = useRouter();
  // Primary builder selection
  const [builderType, setBuilderType] = useState<BuilderType>("character");
  // Character-only ability inputs
  const [rollMode, setRollMode] = useState<RollMode>("auto");
  const [manualRolls, setManualRolls] = useState<string[]>(["", "", "", "", "", ""]);
  const [abilities, setAbilities] = useState<Record<string, string>>({
    STR: "",
    DEX: "",
    CON: "",
    INT: "",
    WIS: "",
    CHA: "",
  });

  const [race, setRace] = useState("");
  const [klass, setKlass] = useState("");
  const [level, setLevel] = useState<number | "">("");
  const [alignment, setAlignment] = useState("");
  const [concept, setConcept] = useState("");
  const [gender, setGender] = useState("");
  const [ageGroup, setAgeGroup] = useState("");

  const [enemyDetails, setEnemyDetails] = useState({
    creatureType: "",
    challenge: "",
    environment: "",
    tactics: "",
  });
  const [npcDetails, setNpcDetails] = useState({
    role: "",
    demeanor: "",
    tie: "",
  });

  const [loading, setLoading] = useState(false);
  const [loadingPhraseIndex, setLoadingPhraseIndex] = useState(0);
  const [loadingDots, setLoadingDots] = useState("");
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [backendUp, setBackendUp] = useState<boolean | null>(null);

  useEffect(() => {
    const ping = async () => {
      try {
        const res = await fetch("/api/health", { cache: "no-store" });
        setBackendUp(res.ok);
      } catch {
        setBackendUp(false);
      }
    };
    ping();
    const id = setInterval(ping, 15000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!loading) {
      setLoadingDots("");
      setLoadingPhraseIndex(0);
      return;
    }

    const dotsTimer = setInterval(() => {
      setLoadingDots((prev) => (prev.length >= 3 ? "" : `${prev}.`));
    }, 450);

    const phraseTimer = setInterval(() => {
      setLoadingPhraseIndex((prev) => (prev + 1) % loadingPhrases.length);
    }, 2200);

    return () => {
      clearInterval(dotsTimer);
      clearInterval(phraseTimer);
    };
  }, [loading]);

  const handleManualRollChange = (index: number, value: string) => {
    const next = [...manualRolls];
    next[index] = value;
    setManualRolls(next);
  };

  const handleAbilityAssignChange = (key: string, value: string) => {
    setAbilities((prev) => ({ ...prev, [key]: value }));
  };

  const buildConcept = () => {
    // Collate freeform flavor plus type-specific hints
    const pieces: string[] = [];
    if (concept.trim()) pieces.push(`Concept: ${concept.trim()}`);
    if (gender) pieces.push(`Gender: ${gender}`);
    if (ageGroup) pieces.push(`Age group: ${ageGroup}`);

    if (builderType === "enemy") {
      if (enemyDetails.creatureType.trim()) pieces.push(`Creature type: ${enemyDetails.creatureType.trim()}`);
      if (enemyDetails.challenge.trim()) pieces.push(`Difficulty: ${enemyDetails.challenge.trim()}`);
      if (enemyDetails.environment.trim()) pieces.push(`Environment: ${enemyDetails.environment.trim()}`);
      if (enemyDetails.tactics.trim()) pieces.push(`Tactics: ${enemyDetails.tactics.trim()}`);
    }

    if (builderType === "npc") {
      if (npcDetails.role.trim()) pieces.push(`Role: ${npcDetails.role.trim()}`);
      if (npcDetails.demeanor.trim()) pieces.push(`Personality: ${npcDetails.demeanor.trim()}`);
      if (npcDetails.tie.trim()) pieces.push(`Connection to party: ${npcDetails.tie.trim()}`);
    }

    return pieces.length ? pieces.join(" | ") : null;
  };

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (backendUp === false) {
      setError("Backend unavailable. Please wait a moment and try again.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);

    const effectiveRollMode = builderType === "character" ? rollMode : "auto";
    const body: any = {
      entity_type: builderType,
      roll_mode: effectiveRollMode,
      race: builderType === "character" ? race || null : null,
      dnd_class: builderType === "character" ? klass || null : null,
      level: builderType === "character" ? (level === "" ? null : Number(level)) : null,
      alignment: alignment || null,
      concept: buildConcept(),
      gender: gender || null,
      age_group: ageGroup || null,
    };

    if (builderType === "character") {
      if (effectiveRollMode === "manual") {
        body.manual_rolls = manualRolls
          .map((v) => v.trim())
          .filter((v) => v !== "")
          .map((v) => Number(v));

        body.ability_assignment = Object.fromEntries(
          Object.entries(abilities)
            .filter(([, v]) => v.trim() !== "")
            .map(([k, v]) => [k, Number(v)]),
        );
      }

      if (effectiveRollMode === "standard_array") {
        body.manual_rolls = null;
        body.ability_assignment = null;
      }
    }

    try {
      const res = await fetch("/api/generate_character", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const data: GenerateResponse = await res.json();

      if (!res.ok) {
        setError(data.error || "Something went wrong");
      } else {
        setResult(data);
        // Persist latest result for detail view
        if (typeof window !== "undefined") {
          window.localStorage.setItem(
            "cc-latest-result",
            JSON.stringify({ ...data, entity_type: builderType }),
          );
        }
        router.push(`/detail?type=${builderType}`);
      }
    } catch (err) {
      console.error(err);
      setError("Network or server error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen text-slate-50">
      {loading && (
        <div className="fixed inset-0 z-50 grid place-items-center loading-overlay">
          <div className="w-[320px] rounded-2xl border border-[#35355a] bg-[#0e0e17]/80 p-6 text-center pixel-border">
            <div className="potion-wrap">
              <div className="potion-neck" />
              <div className="potion-bottle" />
              <div className="potion-liquid" />
              <div className="potion-glint" />
              <span className="potion-bubble b1" />
              <span className="potion-bubble b2" />
              <span className="potion-bubble b3" />
            </div>
            <p className="mt-4 text-sm uppercase tracking-[0.2em] text-amber-200">
              Conjuring
            </p>
            <p className="mt-2 text-sm text-slate-200">
              {loadingPhrases[loadingPhraseIndex]}
              <span className="loading-ellipsis">{loadingDots}</span>
            </p>
          </div>
        </div>
      )}
      <div className="max-w-6xl mx-auto px-6 pb-12">
        <header className="sticky top-0 z-10 -mx-6 mb-6 bg-[#0b0b13]/85 backdrop-blur border-b border-[#242437] px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="h-12 w-12 rounded-lg bg-[#1b1b2e] border border-[#35355a] grid place-items-center text-amber-300 font-semibold pixel-border">
                CC
              </div>
              <div>
                <p className="text-lg font-semibold tracking-tight">Character Conjuration</p>
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <button className="pixel-btn rounded-lg bg-[#1c1c2f] border border-[#35355a] px-3 py-1.5 hover:bg-[#25253a] transition">
                Sign in
              </button>
              <button className="pixel-btn rounded-lg bg-amber-300 text-[#111] px-3 py-1.5 font-semibold hover:bg-amber-200 transition">
                Log in
              </button>
            </div>
          </div>
        </header>

        <section className="mb-10 space-y-4">
          <p className="text-xs uppercase tracking-[0.3em] text-amber-300">Adventurer's workbench</p>
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div className="space-y-3">
              <h1 className="text-4xl md:text-5xl font-semibold leading-tight">
                Build characters, enemies, and NPCs in a retro tavern UI.
              </h1>
              <p className="max-w-2xl text-slate-300">
                Plug in your ideas, we keep to 5e rules and shape them into ready-to-run sheets. Save when signed in or draft on the fly.
              </p>
              <div className="flex flex-wrap gap-3 text-xs text-slate-300">
                <span className="rounded-full border border-amber-500/60 bg-amber-500/10 px-3 py-1">5e grounded</span>
                <span className="rounded-full border border-[#35355a] px-3 py-1">Quick drafts</span>
                <span className="rounded-full border border-[#35355a] px-3 py-1">Optional login to save</span>
              </div>
            </div>
            <div className="rounded-2xl border border-amber-400/40 bg-amber-400/10 px-4 py-3 text-sm text-amber-100 shadow-lg shadow-amber-900/30">
              Sign in to save, sync, and version your creations. Stay anonymous for quick one-shots.
            </div>
          </div>
        </section>

        <section className="mb-8">
          <div className="grid gap-3 sm:grid-cols-3">
            {builderOptions.map((option) => (
              <button
                key={option.key}
                onClick={() => {
                  setBuilderType(option.key);
                  if (option.key !== "character") {
                    setRollMode("auto");
                  }
                }}
                className={`text-left rounded-xl border px-4 py-4 transition pixel-border ${
                  builderType === option.key
                    ? "border-amber-400/80 bg-amber-400/10"
                    : "border-[#35355a] bg-[#11111b]/70 hover:border-amber-300/60 hover:bg-[#171727]"
                }`}
              >
                <p className="text-sm uppercase tracking-[0.2em] text-slate-400">{option.key}</p>
                <h3 className="text-lg font-semibold">{option.title}</h3>
                <p className="mt-1 text-sm text-slate-300">{option.blurb}</p>
              </button>
            ))}
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[2fr_1fr]">
          <form
            onSubmit={handleSubmit}
            className="space-y-6 rounded-2xl border border-[#35355a] bg-[#11111b]/80 p-6 shadow-xl shadow-black/30 pixel-border"
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Builder</p>
                <h2 className="text-2xl font-semibold">
                  {builderType === "character" && "Player Character"}
                  {builderType === "enemy" && "Enemy / Monster"}
                  {builderType === "npc" && "Non-Player Character"}
                </h2>
              </div>
              <span className="rounded-full border border-amber-400/60 px-3 py-1 text-xs text-amber-200">
                Rules aware
              </span>
            </div>

            {builderType === "character" && (
              <fieldset className="space-y-2">
                <legend className="font-semibold">Ability scores</legend>
                <div className="flex flex-wrap gap-4 text-sm">
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      value="auto"
                      checked={rollMode === "auto"}
                      onChange={() => setRollMode("auto")}
                    />
                    Auto roll
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      value="standard_array"
                      checked={rollMode === "standard_array"}
                      onChange={() => setRollMode("standard_array")}
                    />
                    Standard array (15, 14, 13, 12, 10, 8)
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      value="manual"
                      checked={rollMode === "manual"}
                      onChange={() => setRollMode("manual")}
                    />
                    I will type rolls
                  </label>
                </div>

                {rollMode === "manual" && (
                  <div className="mt-3 space-y-3">
                    <div className="flex flex-wrap gap-2">
                      {manualRolls.map((v, i) => (
                        <input
                          key={i}
                          type="number"
                          className="w-14 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm"
                          value={v}
                          onChange={(e) => handleManualRollChange(i, e.target.value)}
                          placeholder={String(i + 1)}
                        />
                      ))}
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-sm">
                      {abilityKeys.map((key) => (
                        <label key={key} className="flex flex-col gap-1">
                          <span>{key}</span>
                          <input
                            type="number"
                            className="rounded border border-slate-700 bg-slate-950 px-2 py-1"
                            value={abilities[key]}
                            onChange={(e) => handleAbilityAssignChange(key, e.target.value)}
                            placeholder="score"
                          />
                        </label>
                      ))}
                    </div>
                  </div>
                )}
              </fieldset>
            )}

            {builderType === "character" && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <label className="flex flex-col gap-1">
                  Race (optional)
                  <select
                    className="rounded border border-slate-700 bg-slate-950 px-2 py-1"
                    value={race}
                    onChange={(e) => setRace(e.target.value)}
                  >
                    {raceOptions.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt === "" ? "Select race" : opt}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  Class (optional)
                  <select
                    className="rounded border border-slate-700 bg-slate-950 px-2 py-1"
                    value={klass}
                    onChange={(e) => setKlass(e.target.value)}
                  >
                    {classOptions.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt === "" ? "Select class" : opt}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  Level (optional)
                  <select
                    className="rounded border border-slate-700 bg-slate-950 px-2 py-1"
                    value={level}
                    onChange={(e) => {
                      const v = e.target.value;
                      setLevel(v === "" ? "" : Number(v));
                    }}
                  >
                    <option value="">Select level</option>
                    {Array.from({ length: 20 }, (_, i) => i + 1).map((lvl) => (
                      <option key={lvl} value={lvl}>
                        {lvl}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  Alignment (optional)
                  <select
                    className="rounded border border-slate-700 bg-slate-950 px-2 py-1"
                    value={alignment}
                    onChange={(e) => setAlignment(e.target.value)}
                  >
                    {alignmentOptions.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt === "" ? "Select alignment" : opt}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  Gender (optional)
                  <select
                    className="rounded border border-slate-700 bg-slate-950 px-2 py-1"
                    value={gender}
                    onChange={(e) => setGender(e.target.value)}
                  >
                    <option value="">No preference</option>
                    <option value="male">Male</option>
                    <option value="female">Female</option>
                    <option value="nonbinary">Nonbinary</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  Age group (optional)
                  <select
                    className="rounded border border-slate-700 bg-slate-950 px-2 py-1"
                    value={ageGroup}
                    onChange={(e) => setAgeGroup(e.target.value)}
                  >
                    <option value="">No preference</option>
                    <option value="young">Young</option>
                    <option value="adult">Adult</option>
                    <option value="middle-aged">Middle-aged</option>
                    <option value="elder">Elder</option>
                  </select>
                </label>
              </div>
            )}

            {builderType === "enemy" && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <label className="flex flex-col gap-1">
                  Creature type / origin
                  <input
                    className="rounded border border-slate-700 bg-slate-950 px-2 py-1"
                    value={enemyDetails.creatureType}
                    onChange={(e) => setEnemyDetails((p) => ({ ...p, creatureType: e.target.value }))}
                    placeholder="Undead knight, aberration, fiend..."
                  />
                </label>
                <label className="flex flex-col gap-1">
                  Difficulty (CR, party tier, vibe)
                  <input
                    className="rounded border border-slate-700 bg-slate-950 px-2 py-1"
                    value={enemyDetails.challenge}
                    onChange={(e) => setEnemyDetails((p) => ({ ...p, challenge: e.target.value }))}
                    placeholder="CR 5, deadly for level 3s..."
                  />
                </label>
                <label className="flex flex-col gap-1">
                  Environment
                  <input
                    className="rounded border border-slate-700 bg-slate-950 px-2 py-1"
                    value={enemyDetails.environment}
                    onChange={(e) => setEnemyDetails((p) => ({ ...p, environment: e.target.value }))}
                    placeholder="Swamp, astral sea, city rooftops..."
                  />
                </label>
                <label className="flex flex-col gap-1">
                  Signature tactics
                  <input
                    className="rounded border border-slate-700 bg-slate-950 px-2 py-1"
                    value={enemyDetails.tactics}
                    onChange={(e) => setEnemyDetails((p) => ({ ...p, tactics: e.target.value }))}
                    placeholder="Ambush grapples, fire magic, minions..."
                  />
                </label>
              </div>
            )}

            {builderType === "npc" && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                <label className="flex flex-col gap-1">
                  Role
                  <input
                    className="rounded border border-slate-700 bg-slate-950 px-2 py-1"
                    value={npcDetails.role}
                    onChange={(e) => setNpcDetails((p) => ({ ...p, role: e.target.value }))}
                    placeholder="Quest giver, rival, patron..."
                  />
                </label>
                <label className="flex flex-col gap-1">
                  Personality
                  <input
                    className="rounded border border-slate-700 bg-slate-950 px-2 py-1"
                    value={npcDetails.demeanor}
                    onChange={(e) => setNpcDetails((p) => ({ ...p, demeanor: e.target.value }))}
                    placeholder="Gruff veteran, excitable scholar..."
                  />
                </label>
                <label className="flex flex-col gap-1">
                  Tie to party
                  <input
                    className="rounded border border-slate-700 bg-slate-950 px-2 py-1"
                    value={npcDetails.tie}
                    onChange={(e) => setNpcDetails((p) => ({ ...p, tie: e.target.value }))}
                    placeholder="Owes a favor, mentor, nemesis..."
                  />
                </label>
              </div>
            )}

            <div className="space-y-2 text-sm">
              <label className="flex flex-col gap-1">
                Short concept / vibe
                <textarea
                  className="min-h-[80px] rounded border border-slate-700 bg-slate-950 px-2 py-1"
                  value={concept}
                  onChange={(e) => setConcept(e.target.value)}
                  placeholder={
                    builderType === "character"
                      ? "Example: socially anxious wizard who became a hero by accident..."
                      : builderType === "enemy"
                        ? "Example: cursed guardian bound to a ruined temple..."
                        : "Example: gnome artificer who trades rumors for inventions..."
                  }
                />
              </label>
              <p className="text-xs text-slate-400">Choices are optional but will be honored if provided.</p>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="pixel-btn inline-flex items-center justify-center gap-2 rounded-xl bg-amber-300 px-4 py-2 text-sm font-semibold text-[#111] shadow-lg shadow-amber-900/30 transition hover:bg-amber-200 disabled:opacity-60"
            >
              {loading ? "Conjuring..." : `Generate ${builderType}`}
            </button>
          </form>

          <div className="space-y-4">
            {error && (
              <div className="rounded-xl border border-red-800 bg-red-950/60 p-3 text-sm text-red-200 pixel-border">
                {error}
              </div>
            )}

            {result && (
              <div className="rounded-2xl border border-[#35355a] bg-[#11111b]/80 p-4 space-y-3 text-sm pixel-border">
                <div className="flex items-center justify-between">
                  <h2 className="text-base font-semibold">Result</h2>
                  <span className="rounded-full border border-slate-700 px-2 py-0.5 text-xs text-slate-300">
                    {builderType}
                  </span>
                </div>
                {result.question && (
                  <div className="space-y-1">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Prompt</p>
                    <p className="whitespace-pre-wrap text-slate-300">{result.question}</p>
                  </div>
                )}
                {result.answer && (
                  <div className="space-y-1">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Output</p>
                    <p className="whitespace-pre-wrap">{result.answer}</p>
                  </div>
                )}
              </div>
            )}

            {!result && !error && (
              <div className="rounded-2xl border border-[#35355a] bg-[#0c0c14]/80 p-4 text-sm text-slate-300 pixel-border">
                <p className="font-semibold text-slate-100">How it works</p>
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  <li>Pick Character, Enemy, or NPC to shape the prompt.</li>
                  <li>Enter as little or as much detail as you like.</li>
                  <li>We stick to 5e rules and hand back a ready-to-run blurb.</li>
                </ul>
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
