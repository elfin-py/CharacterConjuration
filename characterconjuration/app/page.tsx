"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import NavBar from "./components/NavBar";
import Footer from "./components/Footer";

type RollMode = "auto" | "standard_array" | "manual" | "point_buy";
type BuilderType = "character" | "enemy" | "npc";

interface GenerateResponse {
  question?: string;
  answer?: string;
  error?: string;
  [key: string]: any;
}

const abilityKeys = ["STR", "DEX", "CON", "INT", "WIS", "CHA"] as const;
const standardArray = [15, 14, 13, 12, 10, 8];
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
  const displayEntityType = (value: BuilderType) => (value === "npc" ? "NPC" : value);
  // Primary builder selection
  const [builderType, setBuilderType] = useState<BuilderType>("character");
  // Character-only ability inputs
  const [rollMode, setRollMode] = useState<RollMode>("auto");
  const [abilities, setAbilities] = useState<Record<string, string>>({
    STR: "",
    DEX: "",
    CON: "",
    INT: "",
    WIS: "",
    CHA: "",
  });
  const [standardAssignments, setStandardAssignments] = useState<Record<string, string>>({
    STR: "",
    DEX: "",
    CON: "",
    INT: "",
    WIS: "",
    CHA: "",
  });
  const [pointBuyScores, setPointBuyScores] = useState<Record<string, number>>({
    STR: 8,
    DEX: 8,
    CON: 8,
    INT: 8,
    WIS: 8,
    CHA: 8,
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

  const handleAbilityAssignChange = (key: string, value: string) => {
    setAbilities((prev) => ({ ...prev, [key]: value }));
  };

  const handleStandardAssignChange = (key: string, value: string) => {
    setStandardAssignments((prev) => ({ ...prev, [key]: value }));
  };

  const pointBuyCost = (score: number) => {
    if (score <= 13) return score - 8;
    if (score === 14) return 7;
    if (score === 15) return 9;
    return 0;
  };

  const totalPointBuyCost = Object.values(pointBuyScores).reduce((acc, score) => acc + pointBuyCost(score), 0);
  const pointsRemaining = 27 - totalPointBuyCost;

  const adjustPointBuy = (key: string, delta: number) => {
    setPointBuyScores((prev) => {
      const current = prev[key];
      const nextScore = Math.min(15, Math.max(8, current + delta));
      if (nextScore === current) return prev;
      const currentTotal = Object.values(prev).reduce((acc, score) => acc + pointBuyCost(score), 0);
      const nextTotal = currentTotal - pointBuyCost(current) + pointBuyCost(nextScore);
      if (nextTotal > 27) return prev;
      return { ...prev, [key]: nextScore };
    });
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
      if (effectiveRollMode === "standard_array") {
        const values = Object.values(standardAssignments).filter((v) => v !== "");
        const unique = new Set(values);
        const isValid =
          values.length === 6 &&
          unique.size === 6 &&
          values.every((v) => standardArray.includes(Number(v)));
        if (!isValid) {
          setError("Assign each standard array value (15, 14, 13, 12, 10, 8) exactly once.");
          return;
        }
      }
      if (effectiveRollMode === "manual") {
        body.ability_assignment = Object.fromEntries(
          Object.entries(abilities)
            .filter(([, v]) => v.trim() !== "")
            .map(([k, v]) => [k, Number(v)]),
        );
      }

      if (effectiveRollMode === "standard_array") {
        body.manual_rolls = null;
        body.ability_assignment = Object.fromEntries(
          Object.entries(standardAssignments).map(([k, v]) => [k, Number(v)]),
        );
      }

      if (effectiveRollMode === "point_buy") {
        body.manual_rolls = null;
        body.ability_assignment = { ...pointBuyScores };
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
    <main className="min-h-screen text-[color:var(--text)]">
      {loading && (
        <div className="fixed inset-0 z-50 grid place-items-center loading-overlay">
          <div className="w-[320px] rounded-2xl cc-card cc-vignette p-6 text-center">
            <div className="loader mx-auto" />
            <p className="mt-4 text-sm uppercase tracking-[0.2em] cc-ink">
              Conjuring
            </p>
            <p className="mt-2 text-sm cc-ink">
              {loadingPhrases[loadingPhraseIndex]}
              <span className="loading-ellipsis">{loadingDots}</span>
            </p>
          </div>
        </div>
      )}
      <NavBar />

      <div className="max-w-6xl mx-auto px-6 pb-12 min-h-[calc(100vh-120px)]">
        <section className="mt-8 mb-10 space-y-4 rounded-2xl cc-card cc-vignette p-6">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div className="space-y-3">
              <h1 className="text-4xl md:text-5xl font-semibold leading-tight cc-title cc-ink">
                Build characters, enemies, and NPCs at the flick of a wrist.
              </h1>
              <p className="max-w-2xl cc-paragraph cc-ink text-sm">
                Choose Character, Enemy, or NPC, add any details you want, then hit Generate. The tool creates a rules‑aware profile for your campaign.
              </p>
            </div>
            <div className="rounded-2xl cc-card-muted px-4 py-3 text-sm cc-ink">
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
                className={`text-left rounded-xl px-4 py-4 transition cc-card cc-paper ${
                  builderType === option.key
                    ? "ring-2 ring-[color:var(--accent)]/70"
                    : "hover:brightness-110"
                }`}
              >
                <p className="text-sm uppercase tracking-[0.2em] text-[color:var(--text)]/60">{option.key}</p>
                <h3 className="text-lg font-semibold cc-title">{option.title}</h3>
                <p className="mt-1 text-sm text-[color:var(--text)]/80">{option.blurb}</p>
              </button>
            ))}
          </div>
        </section>

        <section className="grid gap-6">
          <form
            onSubmit={handleSubmit}
            className="space-y-6 rounded-2xl cc-card cc-vignette p-6"
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="cc-ornament">Builder</p>
                <h2 className="text-2xl font-semibold cc-title">
                  {builderType === "character" && "Player Character"}
                  {builderType === "enemy" && "Enemy / Monster"}
                  {builderType === "npc" && "Non-Player Character"}
                </h2>
              </div>
            </div>
            <div className="cc-divider" />

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
                      value="point_buy"
                      checked={rollMode === "point_buy"}
                      onChange={() => setRollMode("point_buy")}
                    />
                    Point buy (27 points)
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      value="manual"
                      checked={rollMode === "manual"}
                      onChange={() => setRollMode("manual")}
                    />
                    Manual Input
                  </label>
                </div>

                {rollMode === "standard_array" && (
                  <div className="mt-3 space-y-3">
                    <p className="text-xs text-[color:var(--text)]/70">
                      Assign each value once.
                    </p>
                    <div className="grid grid-cols-3 gap-2 text-sm">
                      {abilityKeys.map((key) => {
                        const used = new Set(
                          Object.entries(standardAssignments)
                            .filter(([k]) => k !== key)
                            .map(([, v]) => v)
                            .filter((v) => v !== ""),
                        );
                        return (
                          <label key={key} className="flex flex-col gap-1">
                            <span>{key}</span>
                            <select
                              className="rounded px-2 py-1 cc-form-field"
                              value={standardAssignments[key]}
                              onChange={(e) => handleStandardAssignChange(key, e.target.value)}
                            >
                              <option value="">Select</option>
                              {standardArray.map((value) => (
                                <option key={value} value={value} disabled={used.has(String(value))}>
                                  {value}
                                </option>
                              ))}
                            </select>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                )}

                {rollMode === "point_buy" && (
                  <div className="mt-3 space-y-3">
                    <div className="flex items-center justify-between text-xs text-[color:var(--text)]/70">
                      <span>Spend 27 points (8–15 each)</span>
                      <span className={pointsRemaining < 0 ? "text-red-400" : "text-emerald-500"}>
                        {pointsRemaining} points remaining
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      {abilityKeys.map((key) => (
                        <div key={key} className="flex items-center justify-between rounded px-2 py-1 cc-form-field">
                          <span>{key}</span>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              className="h-7 w-7 rounded border border-[color:var(--border)] text-[color:var(--text)] hover:brightness-110"
                              onClick={() => adjustPointBuy(key, -1)}
                            >
                              -
                            </button>
                            <span className="w-6 text-center">{pointBuyScores[key]}</span>
                            <button
                              type="button"
                              className="h-7 w-7 rounded border border-[color:var(--border)] text-[color:var(--text)] hover:brightness-110"
                              onClick={() => adjustPointBuy(key, 1)}
                            >
                              +
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {rollMode === "manual" && (
                  <div className="mt-3 space-y-3">
                    <div className="grid grid-cols-3 gap-2 text-sm">
                      {abilityKeys.map((key) => (
                        <label key={key} className="flex flex-col gap-1">
                          <span>{key}</span>
                          <input
                            type="number"
                            className="rounded px-2 py-1 cc-form-field"
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
                    className="rounded px-2 py-1 cc-form-field"
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
                    className="rounded px-2 py-1 cc-form-field"
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
                    className="rounded px-2 py-1 cc-form-field"
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
                    className="rounded px-2 py-1 cc-form-field"
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
                    className="rounded px-2 py-1 cc-form-field"
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
                    className="rounded px-2 py-1 cc-form-field"
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
                    className="rounded px-2 py-1 cc-form-field"
                    value={enemyDetails.creatureType}
                    onChange={(e) => setEnemyDetails((p) => ({ ...p, creatureType: e.target.value }))}
                    placeholder="Undead knight, aberration, fiend..."
                  />
                </label>
                <label className="flex flex-col gap-1">
                  Difficulty (CR, party tier, vibe)
                  <input
                    className="rounded px-2 py-1 cc-form-field"
                    value={enemyDetails.challenge}
                    onChange={(e) => setEnemyDetails((p) => ({ ...p, challenge: e.target.value }))}
                    placeholder="CR 5, deadly for level 3s..."
                  />
                </label>
                <label className="flex flex-col gap-1">
                  Environment
                  <input
                    className="rounded px-2 py-1 cc-form-field"
                    value={enemyDetails.environment}
                    onChange={(e) => setEnemyDetails((p) => ({ ...p, environment: e.target.value }))}
                    placeholder="Swamp, astral sea, city rooftops..."
                  />
                </label>
                <label className="flex flex-col gap-1">
                  Signature tactics
                  <input
                    className="rounded px-2 py-1 cc-form-field"
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
                    className="rounded px-2 py-1 cc-form-field"
                    value={npcDetails.role}
                    onChange={(e) => setNpcDetails((p) => ({ ...p, role: e.target.value }))}
                    placeholder="Quest giver, rival, patron..."
                  />
                </label>
                <label className="flex flex-col gap-1">
                  Personality
                  <input
                    className="rounded px-2 py-1 cc-form-field"
                    value={npcDetails.demeanor}
                    onChange={(e) => setNpcDetails((p) => ({ ...p, demeanor: e.target.value }))}
                    placeholder="Gruff veteran, excitable scholar..."
                  />
                </label>
                <label className="flex flex-col gap-1">
                  Tie to party
                  <input
                    className="rounded px-2 py-1 cc-form-field"
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
                  className="min-h-[80px] rounded px-2 py-1 cc-form-field"
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
              <div className="rounded-xl border border-red-800 bg-red-950/60 p-3 text-sm text-red-200">
                {error}
              </div>
            )}

            {result && (
              <div className="rounded-2xl cc-card cc-vignette p-4 space-y-3 text-sm">
                <div className="flex items-center justify-between">
                  <h2 className="text-base font-semibold">Result</h2>
                  <span className="rounded-full border border-[color:var(--border)] px-2 py-0.5 text-xs text-[color:var(--text)]/70">
                    {displayEntityType(builderType)}
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

          </div>
        </section>

      </div>

      <Footer />
    </main>
  );
}
