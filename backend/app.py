"""
FastAPI service that turns user choices into a 5e-friendly description
for characters, enemies, or NPCs. It:
- loads HF credentials and a prebuilt vector index of 5e rules snippets,
- builds a prompt from the structured payload,
- retrieves context, calls the Zephyr chat model, and returns the answer.
"""

import os
import random
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Optional, Dict, List, Tuple

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from huggingface_hub import InferenceClient
from llama_index.core import VectorStoreIndex
import logging
import pickle
from io import BytesIO
from fpdf import FPDF
from fill_pdf import fill_pdf
from index_stubs import NullIndex, NullRetriever
from rules_data import (
    ABILITIES,
    BACKGROUND_SKILLS,
    CLASS_RULES,
    SKILL_TO_ABILITY,
    ability_mod,
    canonical_background_key,
    canonical_class_key,
    canonical_race_key,
    compute_armor_class,
    compute_hit_points,
    build_has_spell_source,
    default_racial_features,
    default_racial_senses,
    dedupe,
    generate_diverse_name,
    generated_fallback_spells_for_build,
    normalize_armor_proficiencies,
    normalize_features_for_build,
    normalize_skill_name,
    normalize_skill_proficiencies,
    normalize_saving_throw_proficiencies,
    normalize_weapon_proficiencies,
    prof_bonus,
    spellcasting_profile,
    validate_spells,
)

# Logger setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parent
EVAL_RESULTS_DIR = BACKEND_DIR / "eval" / "results"

# Load local env (expects backend/.env with HF_TOKEN)
DOTENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(DOTENV_PATH)
HF_TOKEN = os.getenv("HF_TOKEN")
if not HF_TOKEN:
    raise RuntimeError("HF_TOKEN not set")
HF_MODEL = os.getenv("HF_MODEL", "").strip() or "tiiuae/falcon-7b-instruct"
HF_MODEL_CANDIDATES = [
    m.strip()
    for m in (os.getenv("HF_MODEL_CANDIDATES") or "").split(",")
    if m.strip()
]
if not HF_MODEL_CANDIDATES:
    HF_MODEL_CANDIDATES = [
        HF_MODEL,
        "HuggingFaceH4/zephyr-7b-alpha",
        "tiiuae/falcon-7b-instruct",
        "mistralai/Mistral-7B-Instruct-v0.2",
        "google/gemma-7b-it",
    ]

# Runtime switches
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["PYTORCH_MPS_DISABLE"] = "1"  # avoid Mac MPS pickle mismatches

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", (text or "").lower())


class _TextNode:
    def __init__(self, text: str):
        self.text = text

    def get_content(self):
        return self.text


class MarkdownFallbackRetriever:
    """Simple lexical retriever over markdown files when the vector index is unavailable."""

    def __init__(self, base_dir: Path, top_k: int = 5, chunk_size: int = 1600, chunk_overlap: int = 200):
        self.top_k = top_k
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.documents: list[tuple[str, Counter, set[str]]] = []
        for root in (base_dir / "data" / "split_md", base_dir / "data" / "md"):
            if not root.exists():
                continue
            for path in root.rglob("*.md"):
                text = path.read_text(encoding="utf-8", errors="ignore").strip()
                if not text:
                    continue
                for chunk in self._chunk_text(text):
                    tokens = _tokenize(chunk)
                    if not tokens:
                        continue
                    self.documents.append((chunk, Counter(tokens), set(tokens)))

    def _chunk_text(self, text: str) -> list[str]:
        if len(text) <= self.chunk_size:
            return [text]
        chunks = []
        step = max(1, self.chunk_size - self.chunk_overlap)
        for start in range(0, len(text), step):
            chunk = text[start : start + self.chunk_size].strip()
            if len(chunk) < 200:
                continue
            last_newline = chunk.rfind("\n")
            if last_newline > 800:
                chunk = chunk[:last_newline].strip()
            chunks.append(chunk)
            if start + self.chunk_size >= len(text):
                break
        return chunks or [text[: self.chunk_size]]

    def retrieve(self, question: str):
        query_tokens = _tokenize(question)
        if not query_tokens or not self.documents:
            return []
        query_counts = Counter(query_tokens)
        query_set = set(query_tokens)
        scored = []
        for text, token_counts, token_set in self.documents:
            overlap = query_set & token_set
            if not overlap:
                continue
            tf_score = sum(min(query_counts[t], token_counts[t]) for t in overlap)
            phrase_bonus = 3 if question and question.lower() in text.lower() else 0
            score = tf_score + phrase_bonus
            if score > 0:
                scored.append((score, text))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [_TextNode(text) for _, text in scored[: self.top_k]]


# Load the serialized index once; if unavailable, keep serving with a markdown fallback
INDEX_PATH = BACKEND_DIR / "character_index.pkl"
retriever_mode = "stub"
try:
    with INDEX_PATH.open("rb") as f:
        index: VectorStoreIndex = pickle.load(f)
    if isinstance(index, NullIndex):
        raise ValueError("character_index.pkl contains the fallback stub index")
    retriever = index.as_retriever(similarity_top_k=5)
    retriever_mode = "vector_index"
except Exception as exc:  # fallback if pickle/device mismatch
    logger.warning("Failed to load character_index.pkl (%s); trying markdown fallback", exc)
    fallback = MarkdownFallbackRetriever(BACKEND_DIR)
    if fallback.documents:
        retriever = fallback
        retriever_mode = "markdown_fallback"
        logger.info("Loaded markdown fallback retriever with %d documents", len(fallback.documents))
    else:
        logger.warning("No markdown documents available; using empty retriever")
        retriever = NullRetriever()

def chat_with_fallback(messages):
    last_err = None
    for model_name in HF_MODEL_CANDIDATES:
        try:
            client = InferenceClient(model=model_name, token=HF_TOKEN)
            resp = client.chat_completion(messages=messages, max_tokens=700)
            return resp.choices[0].message["content"], model_name
        except Exception as exc:
            last_err = exc
            logger.warning("HF model %s failed: %s", model_name, exc)
    raise last_err or RuntimeError("No HF models available")


def retrieve_context(question: str, enabled: bool = True) -> Tuple[str, list[str]]:
    """Return joined retrieval context and the raw retrieved snippets."""
    if not enabled:
        return "", []

    nodes = retriever.retrieve(question)
    context_parts = []
    raw_sources = []
    for i, n in enumerate(nodes, start=1):
        try:
            text = n.get_content()
        except AttributeError:
            text = getattr(n.node, "text", "")
        text = (text or "").strip()
        if not text:
            continue
        raw_sources.append(text)
        context_parts.append(f"--- Source {i} ---\n{text}")
    return "\n\n".join(context_parts), raw_sources

app = FastAPI()


class GenerateRequest(BaseModel):
    entity_type: str = "character"          # "character" | "enemy" | "npc"
    roll_mode: str                           # "auto" | "standard_array" | "manual" | "point_buy"
    experimental_mode: str = "validated_iterative_rag"  # "no_rag" | "rag" | "validated_iterative_rag"
    manual_rolls: Optional[List[int]] = None
    ability_assignment: Optional[Dict[str, int]] = None  # {"STR": 15, ...}
    race: Optional[str] = None
    dnd_class: Optional[str] = None
    level: Optional[int] = None
    alignment: Optional[str] = None
    concept: Optional[str] = None
    gender: Optional[str] = None            # "male" | "female" | "nonbinary"
    age_group: Optional[str] = None         # "young", "adult", "middle-aged", "elder"


class SheetRequest(BaseModel):
    sheet_json: dict


def sample_default_level() -> int:
    return max(1, min(20, round(random.triangular(1, 20, 6))))


def build_question(req: GenerateRequest) -> str:
    """Turn the user choices into a single natural language prompt."""
    bits = []

    entity_type = (req.entity_type or "character").strip().lower()
    if entity_type not in {"character", "enemy", "npc"}:
        entity_type = "character"

    if req.level:
        bits.append(f"level {req.level}")
    if req.race:
        bits.append(req.race)
    if req.dnd_class:
        bits.append(req.dnd_class)

    if bits:
        base = " ".join(bits)
    elif entity_type == "enemy":
        base = "Dungeons and Dragons 5e enemy or monster"
    elif entity_type == "npc":
        base = "Dungeons and Dragons 5e non-player character"
    else:
        base = "Dungeons and Dragons 5e character"

    desc = req.concept or "interesting but mechanically sound"
    question = f"Create a {base} with the following concept: {desc}."

    constraints = []
    constraints.append(f"entity_type={entity_type}")
    constraints.append(f"roll_mode={req.roll_mode}")
    if req.gender:
        constraints.append(f"gender={req.gender}")
    if req.age_group:
        constraints.append(f"age_group={req.age_group}")
    if req.manual_rolls:
        constraints.append(f"manual_rolls={req.manual_rolls}")
    if req.ability_assignment:
        constraints.append(f"ability_assignment={req.ability_assignment}")
    if req.alignment:
        constraints.append(f"alignment={req.alignment}")
    question += " Constraints: " + "; ".join(constraints) + "."

    # Add ability guidance for the model
    if req.roll_mode == "standard_array":
        question += " Use the standard array (15, 14, 13, 12, 10, 8) for abilities; assign logically."
    elif req.roll_mode == "point_buy":
        question += " Use the 27-point buy system (8-15 before bonuses) for abilities."
    elif req.roll_mode == "manual":
        if req.manual_rolls:
            question += f" Use these rolled scores {req.manual_rolls} for abilities."
        if req.ability_assignment:
            question += f" Apply this assignment: {req.ability_assignment}."
    else:
        question += " Roll suitable ability scores automatically (4d6 drop lowest style) and assign logically."

    question += " Respect the 5e rules in the provided context."

    return question


def normalize_experimental_mode(mode: str) -> str:
    value = (mode or "rag").strip().lower()
    if value not in {"no_rag", "rag", "validated_iterative_rag"}:
        return "rag"
    return value


def build_messages(question: str, context: str, validation_feedback: Optional[str] = None):
    system_parts = [
        "You are a Dungeons and Dragons 5e builder.",
        "Use only the provided context (PHB and related books) when context is available.",
        "Always return STRICT JSON only (no markdown, no prose) exactly matching this shape:\n"
        "{\n"
        "  \"name\": \"First Last\" (use a believable first+last name appropriate to the chosen race),\n"
        "  \"race\": \"...\",  // choose based on user input if provided; otherwise pick a fitting race from context\n"
        "  \"class\": \"...\", // do NOT copy this example; choose a class that fits the request; never default to wizard unless user asked\n"
        "  \"subclass\": \"...\" (use a suitable subclass to the chosen class),\n"
        "  \"level\": 6,  // if user did not give a level, pick a plausible random level centered around 6\n"
        "  \"background\": \"...\", // select a background that appears in the provided context/books; reject placeholders like Unspecified or generic Sage unless explicitly requested\n"
        "  \"alignment\": \"Chaotic Good\",  // use full words, no abbreviations; honour provided alignment if given\n"
        "  \"hp\": 32,\n"
        "  \"ac\": 15,\n"
        "  \"speed\": 30,\n"
        "  \"stats\": {\"STR\":8,\"DEX\":14,\"CON\":12,\"INT\":16,\"WIS\":13,\"CHA\":10},\n"
        "  \"size\": \"Medium\", // size category for the creature (Small/Medium/Large/etc.)\n"
        "  \"creature_type\": \"humanoid (goblinoid)\", // for enemies/monsters only\n"
        "  \"challenge_rating\": \"1/2\", // for enemies/monsters only\n"
        "  \"senses\": \"darkvision 60 ft., passive Perception 10\", // for enemies/monsters only\n"
        "  \"proficiencies\": [\"Arcana\",\"History\"],\n"
        "  \"skill_proficiencies\": [\"History\", \"Perception\"], // explicit skill proficiencies by name\n"
        "  \"saving_throw_proficiencies\": [\"WIS\", \"CHA\"],\n"
        "  \"weapon_proficiencies\": [\"Simple weapons\", \"Longsword\"],\n"
        "  \"armor_proficiencies\": [\"Light armor\", \"Medium armor\", \"Shields\"],\n"
        "  \"languages\": [\"Common\", \"Elvish\"],\n"
        "  \"features\": [\"Sculpt Spells\",\"Arcane Recovery\"],  // include feats or ASIs here when applicable\n"
        "  \"equipment\": [\"Quarterstaff\",\"Spellbook\"],\n"
        "  \"attacks\": [{\"name\":\"Quarterstaff\",\"attack_bonus\":3,\"damage\":\"1d6+1 bludgeoning\"}],\n"
        "  \"spells\": {\"cantrip\": [\"Fire Bolt\"], \"1\": [\"Shield\",\"Magic Missile\"]},\n"
        "  \"gender\": \"...\" (male, female, or nonbinary as requested or fitting),\n"
        "  \"age_group\": \"...\" (young, adult, middle-aged, elder; pick something plausible for race/level),\n"
        "  \"short_blurb\": \"Write a sizable descriptive paragraph (4-6 sentences). Build on the user's concept if provided, and weave age, race, class, subclass, background, goals, and a memorable detail or flaw.\"\n"
        "}\n"
        "- stats must be an object with STR, DEX, CON, INT, WIS, CHA integers (not strings).\n"
        "- hp, ac, speed, level must be integers (not strings).\n"
        "- Use a SINGLE class unless the user explicitly requests multiclass; otherwise choose one class/subclass that fits and matches the given race/background/alignment and concept (avoid defaulting to wizard or repeating the example). Never leave example placeholders in the final JSON.\n"
        "- If level allows feats or ASIs and choices are implied or necessary, add them to the features array (include the feat names or note \"ASI\" with the adjusted scores).\n"
        "- Prefer backgrounds, languages, spells, and gear found in the provided context/books.\n"
        "- If entity_type is NPC, still fill the schema with NPC-appropriate class/background. If enemy, use class='enemy', include size/creature_type/challenge_rating/senses, and fill stats similarly.\n"
        "- Keep short_blurb to 4-6 full sentences; do not return fragmentary blurbs.\n"
        "- Never put spells in the wrong level bucket. Cantrips must be in 'cantrip'; leveled spells must be under their numeric level.\n"
        "- Never assign spells from the wrong class or subclass spell source.\n"
        "Respond with JSON only, no commentary.",
    ]
    if validation_feedback:
        system_parts.append(
            "The previous draft failed validation. Correct the JSON using this feedback and return a fully corrected replacement only:\n"
            f"{validation_feedback}"
        )

    return [
        {"role": "system", "content": " ".join(system_parts)},
        {
            "role": "user",
            "content": f"Context:\n{context or '(no retrieved context)'}\n\nQuestion: {question}",
        },
    ]


def parse_model_json(raw: str):
    parsed = None

    def longest_balanced_prefix(text: str) -> str:
        brace = bracket = 0
        in_str = False
        last_good = None
        for i, ch in enumerate(text):
            if ch == '"' and (i == 0 or text[i - 1] != "\\"):
                in_str = not in_str
            if in_str:
                continue
            if ch == "{":
                brace += 1
            elif ch == "}":
                brace -= 1
            elif ch == "[":
                bracket += 1
            elif ch == "]":
                bracket -= 1
            if brace == 0 and bracket == 0:
                last_good = i
        if last_good is not None:
            return text[: last_good + 1]
        return text

    try:
        parsed = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*", raw, re.S)
        if m:
            candidate = longest_balanced_prefix(m.group(0))
            try:
                parsed = json.loads(candidate)
            except Exception:
                parsed = None

    if isinstance(parsed, dict):
        return parsed

    def grab(key, default=None):
        match = re.search(rf'"{key}"\s*:\s*"([^"]+)"', raw, re.I)
        return match.group(1) if match else default

    def grab_int(key, default=None):
        match = re.search(rf'"{key}"\s*:\s*([0-9]+)', raw, re.I)
        return int(match.group(1)) if match else default

    stats_obj = {}
    for key in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
        stats_obj[key] = grab_int(key)
    return {
        "name": grab("name"),
        "race": grab("race"),
        "class": grab("class"),
        "subclass": grab("subclass"),
        "background": grab("background"),
        "alignment": grab("alignment"),
        "hp": grab_int("hp"),
        "ac": grab_int("ac"),
        "speed": grab_int("speed"),
        "stats": stats_obj,
        "proficiencies": [],
        "features": [],
        "equipment": [],
        "short_blurb": grab("short_blurb"),
        "gender": grab("gender"),
        "age_group": grab("age_group"),
    }


def build_fallback_blurb(req: GenerateRequest, *, race: str, class_name: str, subclass: str, background: str, alignment: str, entity_type: str) -> str:
    concept = (req.concept or "a memorable role in the setting").strip().rstrip(".")
    if entity_type == "enemy":
        parts = [
            f"This {race.lower() if race else 'creature'} threat is framed around {concept}.",
            f"It is presented as a {alignment.lower()} {subclass.lower() + ' ' if subclass else ''}{class_name.lower() if class_name else 'enemy'} with a clear battlefield identity.",
            "Its traits and actions are intended to read like a compact 5e stat block rather than a player-character sheet.",
            "The result favors immediate table use, with concrete combat flavor and a distinct encounter role.",
        ]
    else:
        role = f"{subclass} {class_name}".strip() if subclass else class_name
        parts = [
            f"This {race.lower() if race else 'character'} {role.lower() if role else 'adventurer'} is built around {concept}.",
            f"The background of {background.lower() if background else 'an uncertain past'} shapes how they approach danger, allies, and responsibility.",
            f"The characterization aims for a {alignment.lower()} tone with enough specificity to support role-play at the table.",
            "The final build is written to feel mechanically grounded while still leaving room for player interpretation and growth.",
        ]
    return " ".join(parts)


def count_spell_entries(spells: dict) -> tuple[int, int]:
    cantrips = 0
    leveled = 0
    for bucket, names in (spells or {}).items():
        if str(bucket).lower() in {"0", "cantrip", "cantrips"}:
            cantrips += len(names or [])
        else:
            leveled += len(names or [])
    return cantrips, leveled


def collect_validation_issues(parsed: dict, req: GenerateRequest) -> list[str]:
    issues = []
    if not isinstance(parsed, dict):
        return ["response was not a JSON object"]

    entity_type = (req.entity_type or "").lower()
    required_fields = ["name", "race", "alignment", "short_blurb"]
    if entity_type != "enemy":
        required_fields.append("background")

    for field in required_fields:
        value = parsed.get(field)
        if not value or not str(value).strip():
            issues.append(f"missing {field}")

    level = parsed.get("level") or req.level
    try:
        if level is None or int(level) <= 0:
            issues.append("missing or invalid level")
            level_int = 0
        else:
            level_int = int(level)
    except Exception:
        issues.append("missing or invalid level")
        level_int = 0

    stats = parsed.get("stats") or {}
    if not isinstance(stats, dict):
        issues.append("stats missing or invalid")
        stats = {}
    else:
        for ability in ABILITIES:
            value = stats.get(ability)
            try:
                if value is None:
                    raise ValueError
                int(value)
            except Exception:
                issues.append(f"missing or invalid {ability}")

    placeholders = {"unspecified", "unknown", "n/a", "none"}
    for field in ["background", "race", "class", "name"]:
        value = parsed.get(field)
        if isinstance(value, str) and value.strip().lower() in placeholders:
            issues.append(f"placeholder {field}")

    if entity_type == "enemy":
        if not parsed.get("creature_type"):
            issues.append("enemy missing creature_type")
        if not parsed.get("challenge_rating"):
            issues.append("enemy missing challenge_rating")

    if isinstance(parsed.get("short_blurb"), str):
        sentence_count = len([s for s in re.split(r"[.!?]+", parsed["short_blurb"]) if s.strip()])
        if sentence_count < 4:
            issues.append("short_blurb too short")
    else:
        issues.append("short_blurb too short")

    class_key = canonical_class_key(parsed.get("class") or req.dnd_class or "")
    race_key = canonical_race_key(parsed.get("race") or req.race or "")
    background_text = parsed.get("background") or ""
    subclass = parsed.get("subclass") or ""

    if entity_type != "enemy":
        normalized_skill_profs, invalid_skill_profs, _ = normalize_skill_proficiencies(
            parsed.get("skill_proficiencies") or [],
            class_key,
            background_text,
        )
        if invalid_skill_profs:
            issues.append(f"invalid skill proficiencies: {', '.join(invalid_skill_profs)}")

        if class_key:
            expected_count = (CLASS_RULES.get(class_key) or {}).get("skill_count")
            background_key = canonical_background_key(background_text)
            background_skills = BACKGROUND_SKILLS.get(background_key, [])
            if expected_count is not None:
                max_skills = expected_count + len(background_skills)
                if len(normalized_skill_profs) > max_skills:
                    issues.append("too many skill proficiencies")

        normalized_save_profs, invalid_save_profs = normalize_saving_throw_proficiencies(
            parsed.get("saving_throw_proficiencies") or [],
            class_key,
        )
        if invalid_save_profs:
            issues.append(f"invalid saving throw proficiencies: {', '.join(invalid_save_profs)}")
        if class_key and normalized_save_profs != sorted((CLASS_RULES.get(class_key) or {}).get("saving_throws") or []):
            issues.append("saving throw proficiencies do not match class")

        _, invalid_weapon_profs = normalize_weapon_proficiencies(
            parsed.get("weapon_proficiencies") or [],
            class_key,
            race_key,
        )
        if invalid_weapon_profs:
            issues.append(f"invalid weapon proficiencies: {', '.join(map(str, invalid_weapon_profs))}")

        _, invalid_armor_profs = normalize_armor_proficiencies(
            parsed.get("armor_proficiencies") or [],
            class_key,
        )
        if invalid_armor_profs:
            issues.append(f"invalid armor proficiencies: {', '.join(map(str, invalid_armor_profs))}")

    if entity_type != "enemy" and class_key and level_int > 0 and all(ability in stats for ability in ABILITIES):
        ability_mods = {ability: ability_mod(int(stats[ability])) for ability in ABILITIES}
        spell_source = build_has_spell_source(
            class_key,
            subclass,
            race_key,
            parsed.get("features") or [],
        )
        spellcasting_cfg = spellcasting_profile(class_key, subclass) or {}
        spell_issues, _, capacity = validate_spells(
            parsed.get("spells") or {},
            class_key,
            level_int,
            ability_mods.get(spellcasting_cfg.get("ability", ""), 0),
            subclass,
        )
        issues.extend(spell_issues)
        if not spell_source and parsed.get("spells"):
            issues.append("noncaster has spell entries")
        if spell_source and capacity["non_cantrip_limit"] > 0:
            non_cantrip_count = sum(
                len(names)
                for bucket, names in (parsed.get("spells") or {}).items()
                if str(bucket).lower() not in {"0", "cantrip", "cantrips"}
            )
            if non_cantrip_count == 0:
                issues.append("spell source missing leveled spells")
        elif spell_source and capacity["cantrips"] > 0:
            cantrip_count = sum(
                len(names)
                for bucket, names in (parsed.get("spells") or {}).items()
                if str(bucket).lower() in {"0", "cantrip", "cantrips"}
            )
            if cantrip_count == 0:
                issues.append("spell source missing cantrips")

        deterministic_hp, _ = compute_hit_points(class_key, level_int, int(stats["CON"]), parsed_hp=parsed.get("hp"))
        parsed_hp = parsed.get("hp")
        try:
            if deterministic_hp is not None and int(parsed_hp) != int(deterministic_hp):
                issues.append("hit points do not match deterministic class calculation")
        except Exception:
            issues.append("missing or invalid hp")

        deterministic_ac, _ = compute_armor_class(
            class_key,
            parsed.get("subclass") or "",
            {k: int(stats[k]) for k in ABILITIES},
            parsed.get("equipment") or [],
            parsed_ac=parsed.get("ac"),
        )
        try:
            if int(parsed.get("ac")) != int(deterministic_ac):
                issues.append("armor class does not match deterministic equipment calculation")
        except Exception:
            issues.append("missing or invalid ac")

    return dedupe(issues)


def generate_model_output(req: GenerateRequest, question: str):
    mode = normalize_experimental_mode(req.experimental_mode)
    use_retrieval = mode != "no_rag"
    context, retrieved_sources = retrieve_context(question, enabled=use_retrieval)

    attempts = []
    validation_feedback = None
    max_attempts = 3 if mode == "validated_iterative_rag" else 1
    raw = ""
    used_model = ""
    parsed = {}
    validation_issues = []
    best_attempt = None

    for attempt in range(1, max_attempts + 1):
        messages = build_messages(question, context, validation_feedback=validation_feedback)
        try:
            raw, used_model = chat_with_fallback(messages)
        except Exception as exc:
            logger.exception("HF chat_completion failed")
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Upstream model error: {exc}. Configure HF_MODEL or HF_MODEL_CANDIDATES "
                    "with supported chat models."
                ),
            )

        parsed = parse_model_json(raw)
        validation_issues = collect_validation_issues(parsed, req)
        attempt_record = {
            "attempt": attempt,
            "used_model": used_model,
            "validation_issues": validation_issues,
            "raw": raw,
            "parsed": parsed,
        }
        attempts.append(attempt_record)

        if best_attempt is None or len(validation_issues) < len(best_attempt["validation_issues"]):
            best_attempt = attempt_record

        if mode != "validated_iterative_rag" or not validation_issues:
            break

        validation_feedback = "; ".join(validation_issues)

    if best_attempt is not None:
        raw = best_attempt["raw"]
        used_model = best_attempt["used_model"]
        parsed = best_attempt["parsed"]
        validation_issues = best_attempt["validation_issues"]

    return {
        "experimental_mode": mode,
        "context": context,
        "retrieved_sources": retrieved_sources,
        "raw": raw,
        "used_model": used_model,
        "parsed": parsed,
        "validation_issues": validation_issues,
        "attempts": attempts,
        "attempt_count": len(attempts),
    }


@app.post("/generate_character")
def generate_character(req: GenerateRequest):
    question = build_question(req)
    generation = generate_model_output(req, question)
    raw = generation["raw"]
    used_model = generation["used_model"]
    parsed = generation["parsed"]

    # Validate and normalize parsed JSON
    def coerce_int(val):
        try:
            return int(val)
        except Exception:
            return None

    sheet_json = None
    stats_obj = parsed.get("stats") or {}
    if not isinstance(stats_obj, dict):
        # attempt to build from top-level keys if present
        stats_obj = {
            "STR": parsed.get("STR"),
            "DEX": parsed.get("DEX"),
            "CON": parsed.get("CON"),
            "INT": parsed.get("INT"),
            "WIS": parsed.get("WIS"),
            "CHA": parsed.get("CHA"),
        }

    stats_norm: dict[str, int] = {}
    for k in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
        val = coerce_int(stats_obj.get(k))
        if val is None:
            val = 10  # default to average if missing
        stats_norm[k] = val

    def normalize_assignment(assign: dict) -> dict[str, int]:
        normalized = {}
        for key, val in assign.items():
            k = str(key).upper()
            if k in {"STR", "DEX", "CON", "INT", "WIS", "CHA"}:
                v = coerce_int(val)
                if v is not None:
                    normalized[k] = v
        return normalized

    def is_standard_array(assign: dict[str, int]) -> bool:
        target = sorted([15, 14, 13, 12, 10, 8])
        return sorted(assign.values()) == target

    def is_point_buy(assign: dict[str, int]) -> bool:
        costs = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}
        if any(v not in costs for v in assign.values()):
            return False
        return sum(costs[v] for v in assign.values()) <= 27

    if req.ability_assignment and req.roll_mode in {"manual", "standard_array", "point_buy"}:
        normalized = normalize_assignment(req.ability_assignment)
        if set(normalized.keys()) != {"STR", "DEX", "CON", "INT", "WIS", "CHA"}:
            raise HTTPException(status_code=400, detail="Ability assignment must include STR, DEX, CON, INT, WIS, CHA.")
        if req.roll_mode == "standard_array" and not is_standard_array(normalized):
            raise HTTPException(status_code=400, detail="Standard array assignment must use 15,14,13,12,10,8 exactly once.")
        if req.roll_mode == "point_buy" and not is_point_buy(normalized):
            raise HTTPException(status_code=400, detail="Point buy assignment must be 8-15 with total cost <= 27.")
        if req.roll_mode == "manual" and req.manual_rolls:
            pool = [coerce_int(v) for v in req.manual_rolls or []]
            pool = [v for v in pool if v is not None]
            remaining = pool[:]
            ok = True
            for v in normalized.values():
                if v in remaining:
                    remaining.remove(v)
                else:
                    ok = False
                    break
            if not ok:
                raise HTTPException(status_code=400, detail="Manual assignment must use the provided rolls.")
        stats_norm.update(normalized)

    entity_type = (req.entity_type or "character").lower()
    class_name = parsed.get("class")
    if entity_type == "enemy":
        class_name = "enemy"
    elif isinstance(class_name, str) and ("/" in class_name or "(" in class_name) and "multiclass" not in (question.lower()):
        class_name = class_name.split("/")[0].split("(")[0].strip()
    class_key = "" if entity_type == "enemy" else canonical_class_key(class_name or req.dnd_class or "")
    cls_lower = class_key or (parsed.get("class") or "").lower()
    # Enforce multiclass ability minimums (PHB)
    class_min = {
        "barbarian": {"STR": 13},
        "bard": {"CHA": 13},
        "cleric": {"WIS": 13},
        "druid": {"WIS": 13},
        "fighter": {"STR": 13},  # dex route handled below
        "monk": {"DEX": 13, "WIS": 13},
        "paladin": {"STR": 13, "CHA": 13},
        "ranger": {"DEX": 13, "WIS": 13},
        "rogue": {"DEX": 13},
        "sorcerer": {"CHA": 13},
        "warlock": {"CHA": 13},
        "wizard": {"INT": 13},
        "artificer": {"INT": 13},
    }
    for cls, reqs in class_min.items():
        if cls in cls_lower:
            for abil, minimum in reqs.items():
                if stats_norm[abil] < minimum:
                    stats_norm[abil] = minimum
    # Fighter dex route: accept DEX 13 instead of STR 13
    if "fighter" in cls_lower:
        if stats_norm["STR"] < 13 and stats_norm["DEX"] >= 13:
            stats_norm["STR"] = 13  # minimal STR for carry; allow DEX to meet prerequisite
        elif stats_norm["STR"] < 13 and stats_norm["DEX"] < 13:
            stats_norm["DEX"] = 13

    hp = coerce_int(parsed.get("hp")) or 10
    ac = coerce_int(parsed.get("ac")) or 0
    speed = coerce_int(parsed.get("speed")) or 30
    # Default level to a plausible random range if neither the model nor user provided one
    level = coerce_int(parsed.get("level") or req.level)
    if not level:
        level = sample_default_level()
    alignment = parsed.get("alignment") or req.alignment or "Unspecified"
    gender = parsed.get("gender") or req.gender or "Unspecified"
    age_group = parsed.get("age_group") or req.age_group or "Unspecified"
    background = parsed.get("background") or ("Unspecified" if entity_type != "enemy" else "")
    if entity_type != "enemy" and ((not background) or background.lower() in {"unspecified", "sage"}):
        fallback_backgrounds = [
            "Soldier",
            "Criminal",
            "Outlander",
            "Acolyte",
            "Folk Hero",
            "Noble",
            "Hermit",
            "Entertainer",
            "Guild Artisan",
            "Sailor",
            "Urchin",
            "Far Traveler",
            "City Watch",
        ]
        background = random.choice(fallback_backgrounds)
    race = parsed.get("race") or "Unspecified"
    race_key = canonical_race_key(race)
    model_name = str(parsed.get("name") or "").strip()
    generated_name = generate_diverse_name(race_key)
    final_name = generated_name if not model_name or len(model_name.split()) < 2 else generated_name
    proficiencies = parsed.get("proficiencies") or []
    skill_profs = parsed.get("skill_proficiencies") or []
    saving_throw_profs = parsed.get("saving_throw_proficiencies") or []
    weapon_profs = parsed.get("weapon_proficiencies") or []
    armor_profs = parsed.get("armor_proficiencies") or []
    languages = parsed.get("languages") or []
    attacks = parsed.get("attacks") or []
    spells = parsed.get("spells") or {}
    features = parsed.get("features") or []
    equipment = parsed.get("equipment") or []
    subclass = parsed.get("subclass") or ""

    if entity_type == "enemy":
        creature_type = parsed.get("creature_type") or f"humanoid ({(race or 'unknown').lower()})"
        challenge_rating = parsed.get("challenge_rating") or str(max(1, round(level / 2)))
        if not isinstance(spells, dict):
            spells = {}
        # Avoid forcing enemy spell fallback; enemies may be non-spellcasters or use custom powers.
    else:
        creature_type = parsed.get("creature_type")
        challenge_rating = parsed.get("challenge_rating")

    pb = prof_bonus(level)

    # Skills and saves
    skill_profs = [normalize_skill_name(p) for p in (skill_profs or [])]
    profs_lower = [p.lower() for p in (skill_profs or [])]

    def skill_bonus(skill_key: str):
        abil = SKILL_TO_ABILITY[skill_key]
        val = ability_mod(stats_norm[abil])
        if any(skill_key in p for p in profs_lower):
            val += pb
        return val

    if entity_type != "enemy":
        skill_profs, invalid_skill_profs, background_key = normalize_skill_proficiencies(
            skill_profs,
            class_key,
            background,
        )
        profs_lower = [p.lower() for p in skill_profs]
    else:
        invalid_skill_profs = []
        background_key = ""

    skills = {k: skill_bonus(k) for k in SKILL_TO_ABILITY}
    passive_perception = 10 + skills["perception"]

    if entity_type != "enemy":
        saving_throw_profs, invalid_save_profs = normalize_saving_throw_proficiencies(
            saving_throw_profs,
            class_key,
        )
    else:
        invalid_save_profs = []
    save_profs = set(saving_throw_profs)
    saving_throws = {}
    for abil in ABILITIES:
        val = ability_mod(stats_norm[abil])
        if abil in save_profs:
            val += pb
        saving_throws[abil] = val

    if entity_type != "enemy":
        weapon_profs, invalid_weapon_profs = normalize_weapon_proficiencies(weapon_profs, class_key, race_key)
        armor_profs, invalid_armor_profs = normalize_armor_proficiencies(armor_profs, class_key)
        features, feature_corrections = normalize_features_for_build(features, class_key, subclass)
    else:
        invalid_weapon_profs = []
        invalid_armor_profs = []
        feature_corrections = []

    spell_ability = (spellcasting_profile(class_key, subclass) or {}).get("ability")
    spell_save_dc = None
    spell_attack_bonus = None
    if spell_ability:
        spell_mod = ability_mod(stats_norm[spell_ability])
        spell_save_dc = 8 + pb + spell_mod
        spell_attack_bonus = pb + spell_mod

    size = parsed.get("size")
    if not size:
        small_races = {"gnome", "halfling"}
        size = "Small" if (race or "").lower() in small_races else "Medium"

    if entity_type == "enemy":
        hp = coerce_int(parsed.get("hp")) or hp
        hp_provenance = {"source": "model", "reason": "enemy output"}
        ac = coerce_int(parsed.get("ac")) or ac or 10
        ac_provenance = {"source": "model", "reason": "enemy output"}
        spell_issues = []
        normalized_spells = spells if isinstance(spells, dict) else {}
        spell_capacity = {"cantrips": 0, "max_spell_level": 0, "non_cantrip_limit": 0, "rule": "noncaster"}
        used_spell_fallback = False
        spell_source = False
    else:
        hp, hp_provenance = compute_hit_points(class_key, level, stats_norm["CON"], parsed_hp=parsed.get("hp"))
        ac, ac_provenance = compute_armor_class(
            class_key,
            parsed.get("subclass") or "",
            stats_norm,
            equipment,
            parsed_ac=parsed.get("ac"),
        )
        spell_issues, normalized_spells, spell_capacity = validate_spells(
            spells,
            class_key,
            level,
            ability_mod(stats_norm[spell_ability]) if spell_ability else 0,
            subclass,
        )
        if normalized_spells:
            spells = normalized_spells
        used_spell_fallback = False
        spell_source = build_has_spell_source(class_key, subclass, race_key, features)

    if entity_type != "enemy" and spell_source and spell_capacity["rule"] != "noncaster":
        default_spells = generated_fallback_spells_for_build(
            class_key,
            subclass,
            level,
            ability_mod(stats_norm[spell_ability]) if spell_ability else 0,
        )
        if default_spells:
            merged_spells = {bucket: list(names) for bucket, names in (spells or {}).items()}
            for bucket, fallback_names in default_spells.items():
                existing = list(merged_spells.get(bucket) or [])
                limit = spell_capacity["cantrips"] if bucket == "cantrip" else spell_capacity["non_cantrip_limit"]
                for fallback_name in fallback_names:
                    if fallback_name not in existing and len(existing) < limit:
                        existing.append(fallback_name)
                if existing:
                    merged_spells[bucket] = existing
            fallback_issues, fallback_spells, _ = validate_spells(
                merged_spells,
                class_key,
                level,
                ability_mod(stats_norm[spell_ability]) if spell_ability else 0,
                subclass,
            )
            pure_default_issues, pure_default_spells, _ = validate_spells(
                default_spells,
                class_key,
                level,
                ability_mod(stats_norm[spell_ability]) if spell_ability else 0,
                subclass,
            )

            candidate_options = []
            if fallback_spells:
                candidate_options.append((fallback_issues, fallback_spells))
            if pure_default_spells:
                candidate_options.append((pure_default_issues, pure_default_spells))

            if candidate_options:
                def candidate_rank(item):
                    issues, spell_dict = item
                    cantrips, leveled = count_spell_entries(spell_dict)
                    return (len(issues), -(cantrips + leveled), -leveled)

                best_issues, best_spells = min(candidate_options, key=candidate_rank)
                if best_spells != spells:
                    used_spell_fallback = True
                spells = best_spells
                spell_issues = best_issues

    correction_notes = []
    correction_notes.extend(feature_corrections)
    if used_spell_fallback:
        correction_notes.append("filled missing subclass spell selections from fallback rules")
    for racial_feature in default_racial_features(race_key):
        if racial_feature.lower() not in {str(feature).strip().lower() for feature in features}:
            features.append(racial_feature)
            correction_notes.append(f"added default racial feature: {racial_feature}")
    if not parsed.get("senses"):
        default_senses = default_racial_senses(race_key)
        if default_senses:
            correction_notes.append(f"added default racial senses: {default_senses}")
    senses = parsed.get("senses") or default_racial_senses(race_key)
    if invalid_skill_profs:
        correction_notes.append(f"removed invalid skill proficiencies: {', '.join(invalid_skill_profs)}")
    if invalid_save_profs:
        correction_notes.append(f"removed invalid saving throw proficiencies: {', '.join(invalid_save_profs)}")
    if invalid_weapon_profs:
        correction_notes.append(f"removed invalid weapon proficiencies: {', '.join(map(str, invalid_weapon_profs))}")
    if invalid_armor_profs:
        correction_notes.append(f"removed invalid armor proficiencies: {', '.join(map(str, invalid_armor_profs))}")
    if parsed.get("hp") is not None and coerce_int(parsed.get("hp")) != hp:
        correction_notes.append("replaced model hit points with deterministic class calculation")
    if parsed.get("ac") is not None and coerce_int(parsed.get("ac")) != ac:
        correction_notes.append("replaced model armor class with deterministic equipment calculation")
    if normalized_spells and normalized_spells != (parsed.get("spells") or {}):
        correction_notes.append("normalized spell selections to the validated schema")

    short_blurb = parsed.get("short_blurb")
    if not isinstance(short_blurb, str) or len([s for s in re.split(r"[.!?]+", short_blurb) if s.strip()]) < 4:
        short_blurb = build_fallback_blurb(
            req,
            race=race,
            class_name=class_name or "",
            subclass=subclass,
            background=background,
            alignment=alignment,
            entity_type=entity_type,
        )
        correction_notes.append("replaced missing or underspecified short blurb with deterministic fallback text")

    sheet_json = {
        "name": final_name,
        "class": class_name,
        "subclass": parsed.get("subclass"),
        "level": level,
        "race": race,
        "background": background,
        "alignment": alignment,
        "hitPoints": hp,
        "armorClass": ac,
        "speed": speed,
        "size": size,
        "creature_type": creature_type,
        "challenge_rating": challenge_rating,
        "senses": senses,
        "abilities": {
            "str": stats_norm["STR"],
            "dex": stats_norm["DEX"],
            "con": stats_norm["CON"],
            "int": stats_norm["INT"],
            "wis": stats_norm["WIS"],
            "cha": stats_norm["CHA"],
        },
        "proficiencies": proficiencies,
        "skill_proficiencies": skill_profs,
        "saving_throw_proficiencies": saving_throw_profs,
        "weapon_proficiencies": weapon_profs,
        "armor_proficiencies": armor_profs,
        "languages": languages,
        "features": features,
        "equipment": equipment,
        "notes": short_blurb,
        "gender": gender,
        "age_group": age_group,
        "skills": skills,
        "saving_throws": saving_throws,
        "passive_perception": passive_perception,
        "spellcasting_ability": spell_ability,
        "spell_save_dc": spell_save_dc,
        "spell_attack_bonus": spell_attack_bonus,
        "spell_capacity": spell_capacity,
        "attacks": attacks,
        "spells": spells,
        "hit_point_provenance": hp_provenance,
        "armor_class_provenance": ac_provenance,
    }

    final_validation_input = {
        "name": sheet_json["name"],
        "race": sheet_json["race"],
        "class": sheet_json["class"],
        "subclass": sheet_json["subclass"],
        "background": sheet_json["background"],
        "alignment": sheet_json["alignment"],
        "short_blurb": sheet_json["notes"],
        "level": sheet_json["level"],
        "hp": sheet_json["hitPoints"],
        "ac": sheet_json["armorClass"],
        "speed": sheet_json["speed"],
        "size": sheet_json["size"],
        "creature_type": sheet_json["creature_type"],
        "challenge_rating": sheet_json["challenge_rating"],
        "senses": sheet_json["senses"],
        "equipment": sheet_json["equipment"],
        "stats": {ability: stats_norm[ability] for ability in ABILITIES},
        "skill_proficiencies": sheet_json["skill_proficiencies"],
        "saving_throw_proficiencies": sheet_json["saving_throw_proficiencies"],
        "weapon_proficiencies": sheet_json["weapon_proficiencies"],
        "armor_proficiencies": sheet_json["armor_proficiencies"],
        "features": sheet_json["features"],
        "spells": sheet_json["spells"],
    }
    post_validation_issues = collect_validation_issues(final_validation_input, req)

    response = {
        "question": question,
        "answer": raw,
        "parsed": sheet_json,  # normalized values for UI
        "sheet_json": sheet_json,
        "name": sheet_json.get("name"),
        "race": sheet_json.get("race"),
        "class": sheet_json.get("class"),
        "subclass": sheet_json.get("subclass"),
        "level": sheet_json.get("level"),
        "background": sheet_json.get("background"),
        "alignment": sheet_json.get("alignment"),
        "hit_points": sheet_json.get("hitPoints"),
        "armor_class": sheet_json.get("armorClass"),
        "speed": sheet_json.get("speed"),
        "spells": sheet_json.get("spells"),
        "used_model": used_model,
        "experimental_mode": generation["experimental_mode"],
        "validation_issues": post_validation_issues,
        "model_validation_issues": generation["validation_issues"],
        "correction_notes": dedupe(correction_notes),
        "attempt_count": generation["attempt_count"],
        "attempts": generation["attempts"],
        "retrieved_sources": generation["retrieved_sources"],
    }
    if (req.entity_type or "").lower() == "enemy":
        enemy_stat_block = normalize_enemy_stat_block(sheet_json)
        response["enemy_stat_block"] = enemy_stat_block
        response["stat_block"] = build_stat_block(enemy_stat_block)
    response["entity_type"] = req.entity_type
    return response


def build_pdf(sheet: dict) -> bytes:
    """Create a simple one-page PDF from sheet_json."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)

    def line(label, value):
        pdf.cell(0, 10, f"{label}: {value if value is not None else ''}", ln=1)

    line("Name", sheet.get("name", ""))
    line("Class/Subclass", f"{sheet.get('class','')} / {sheet.get('subclass','')}")
    line("Level", sheet.get("level", ""))
    line("Race", sheet.get("race", ""))
    line("Background", sheet.get("background", ""))
    line("Alignment", sheet.get("alignment", ""))
    line("HP / AC / Speed", f"{sheet.get('hitPoints','')} / {sheet.get('armorClass','')} / {sheet.get('speed','')} ft")

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Abilities", ln=1)
    pdf.set_font("Helvetica", size=12)
    abilities = sheet.get("abilities", {})
    for k in ["str", "dex", "con", "int", "wis", "cha"]:
        pdf.cell(32, 8, f"{k.upper()}: {abilities.get(k, '')}", ln=0)
    pdf.ln(10)

    def list_block(title, items):
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, title, ln=1)
        pdf.set_font("Helvetica", size=11)
        for item in items or []:
            pdf.multi_cell(0, 6, f"- {item}")
        pdf.ln(2)

    list_block("Proficiencies", sheet.get("proficiencies"))
    list_block("Features", sheet.get("features"))
    list_block("Equipment", sheet.get("equipment"))

    if sheet.get("notes"):
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Flavour", ln=1)
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 6, sheet["notes"])

    out = BytesIO()
    pdf.output(out)
    return out.getvalue()


def normalize_enemy_stat_block(sheet: dict) -> dict:
    abilities = sheet.get("abilities", {}) or {}

    def fmt_speed(value):
        try:
            return f"{int(value)} ft."
        except Exception:
            return str(value or "—")

    def split_named_entries(items):
        named = []
        for item in items or []:
            text = str(item or "").strip()
            if not text:
                continue
            if "." in text:
                name, body = text.split(".", 1)
                named.append({"name": name.strip(), "text": body.strip()})
            else:
                named.append({"name": text, "text": ""})
        return named

    def normalize_actions(attacks):
        rows = []
        for attack in attacks or []:
            if not isinstance(attack, dict):
                continue
            name = str(attack.get("name") or "Attack").strip()
            bonus = attack.get("attack_bonus")
            damage = str(attack.get("damage") or "").strip()
            body = []
            if bonus is not None:
                body.append(f"+{bonus} to hit")
            if damage:
                body.append(f"Hit: {damage}")
            rows.append({"name": name, "text": ", ".join(body)})
        return rows

    spellcasting = {}
    if sheet.get("spells"):
        spellcasting = {
            "ability": sheet.get("spellcasting_ability"),
            "save_dc": sheet.get("spell_save_dc"),
            "attack_bonus": sheet.get("spell_attack_bonus"),
            "spells": sheet.get("spells") or {},
        }

    return {
        "name": sheet.get("name", "Unknown Creature"),
        "size": sheet.get("size") or "Medium",
        "creature_type": sheet.get("creature_type") or "creature",
        "alignment": sheet.get("alignment") or "Unaligned",
        "armor_class": sheet.get("armorClass", "—"),
        "hit_points": sheet.get("hitPoints", "—"),
        "speed": fmt_speed(sheet.get("speed")),
        "abilities": {
            "STR": abilities.get("str", abilities.get("STR", "—")),
            "DEX": abilities.get("dex", abilities.get("DEX", "—")),
            "CON": abilities.get("con", abilities.get("CON", "—")),
            "INT": abilities.get("int", abilities.get("INT", "—")),
            "WIS": abilities.get("wis", abilities.get("WIS", "—")),
            "CHA": abilities.get("cha", abilities.get("CHA", "—")),
        },
        "saving_throws": sheet.get("saving_throws") or {},
        "skills": sheet.get("skills") or {},
        "skill_proficiencies": sheet.get("skill_proficiencies") or [],
        "senses": sheet.get("senses") or "",
        "languages": sheet.get("languages") or [],
        "challenge_rating": sheet.get("challenge_rating") or "",
        "traits": split_named_entries(sheet.get("features") or []),
        "actions": normalize_actions(sheet.get("attacks") or []),
        "spellcasting": spellcasting,
    }


def build_stat_block(sheet: dict) -> str:
    def mod(score: int) -> str:
        try:
            val = int(score)
        except Exception:
            return "+0"
        return f"{(val - 10) // 2:+d}"

    block = sheet if "armor_class" in sheet else normalize_enemy_stat_block(sheet)
    name = block.get("name", "Unknown Creature")
    size = block.get("size") or "Medium"
    creature_type = block.get("creature_type") or "creature"
    alignment = block.get("alignment") or "Unaligned"
    ac = block.get("armor_class", "—")
    hp = block.get("hit_points", "—")
    speed = block.get("speed", "—")

    abilities = block.get("abilities", {}) or {}
    abil_line = "  ".join(
        f"{k} {abilities.get(k, '—')} ({mod(abilities.get(k, 10))})"
        for k in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
    )

    saving = block.get("saving_throws") or {}
    skills = block.get("skills") or {}
    skill_profs = set(block.get("skill_proficiencies") or [])
    senses = block.get("senses") or ""
    languages = block.get("languages") or []
    cr = block.get("challenge_rating") or ""

    lines = [
        name,
        f"{size} {creature_type}, {alignment}",
        f"Armor Class {ac}",
        f"Hit Points {hp}",
        f"Speed {speed}",
        "",
        abil_line,
        "",
    ]

    if saving:
        save_parts = [f"{abil} {bonus:+d}" for abil, bonus in saving.items()]
        lines.append(f"Saving Throws {', '.join(save_parts)}")
    if skills and skill_profs:
        skill_parts = [f"{skill} {int(skills.get(skill, 0)):+d}" for skill in skill_profs if skill in skills]
        if skill_parts:
            lines.append(f"Skills {', '.join(skill_parts)}")
    if senses:
        lines.append(f"Senses {senses}")
    if languages:
        lines.append(f"Languages {', '.join(languages)}")
    if cr:
        lines.append(f"Challenge {cr}")

    traits = block.get("traits") or []
    actions = block.get("actions") or []
    spellcasting = block.get("spellcasting") or {}

    if traits:
        lines.append("")
        lines.append("Traits")
        for t in traits:
            if t.get("text"):
                lines.append(f"- {t['name']}. {t['text']}")
            else:
                lines.append(f"- {t['name']}")

    if spellcasting.get("spells"):
        lines.append("")
        lines.append("Spellcasting")
        ability = spellcasting.get("ability")
        save_dc = spellcasting.get("save_dc")
        atk_bonus = spellcasting.get("attack_bonus")
        header_bits = []
        if ability:
            header_bits.append(f"Ability {ability}")
        if save_dc is not None:
            header_bits.append(f"Save DC {save_dc}")
        if atk_bonus is not None:
            header_bits.append(f"Spell Attack {atk_bonus:+d}")
        if header_bits:
            lines.append(", ".join(header_bits))
        for lvl, names in spellcasting["spells"].items():
            label = "Cantrips" if str(lvl).lower() in {"0", "cantrip", "cantrips"} else f"Level {lvl}"
            lines.append(f"{label}: {', '.join(names)}")

    if actions:
        lines.append("")
        lines.append("Actions")
        for a in actions:
            if a.get("text"):
                lines.append(f"- {a['name']}. {a['text']}")
            else:
                lines.append(f"- {a['name']}")

    return "\n".join(lines)


@app.post("/fill_statblock")
def fill_statblock(req: SheetRequest):
    if not req.sheet_json:
        raise HTTPException(status_code=400, detail="sheet_json required")
    try:
        stat_text = build_stat_block(req.sheet_json)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Stat block build failed: {exc}")

    from fastapi.responses import Response

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for line in stat_text.splitlines():
        pdf.multi_cell(0, 6, line)
    out = BytesIO()
    pdf.output(out)
    return Response(
        content=out.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=stat_block.pdf"},
    )


@app.post("/fill_sheet")
def fill_sheet(req: SheetRequest):
    if not req.sheet_json:
        raise HTTPException(status_code=400, detail="sheet_json required")

    try:
        pdf_bytes = fill_pdf(req.sheet_json)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Official PDF build failed: {exc}")

    from fastapi.responses import Response

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=5E_CharacterSheet_Fillable_filled.pdf"},
    )


@app.post("/fill_sheet_official")
def fill_sheet_official(req: SheetRequest):
    if not req.sheet_json:
        raise HTTPException(status_code=400, detail="sheet_json required")
    try:
        pdf_bytes = fill_pdf(req.sheet_json)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Official PDF build failed: {exc}")

    from fastapi.responses import Response

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=5E_CharacterSheet_Fillable_filled.pdf"},
    )


@app.get("/health")
def health():
    """Simple health check."""
    return {
        "status": "ok",
        "index_loaded": retriever_mode in {"vector_index", "markdown_fallback"},
        "retriever_mode": retriever_mode,
        "model": HF_MODEL_CANDIDATES[0] if HF_MODEL_CANDIDATES else HF_MODEL,
        "candidate_models": HF_MODEL_CANDIDATES,
    }


def latest_eval_run_dir() -> Optional[Path]:
    if not EVAL_RESULTS_DIR.exists():
        return None
    run_dirs = [path for path in EVAL_RESULTS_DIR.iterdir() if path.is_dir() and path.name.startswith("run_")]
    if not run_dirs:
        return None
    return max(run_dirs, key=lambda path: path.stat().st_mtime)


def load_json_if_exists(path: Path):
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@app.get("/eval/latest")
def eval_latest():
    run_dir = latest_eval_run_dir()
    if run_dir is None:
        raise HTTPException(status_code=404, detail="No evaluation runs found")

    return {
        "run_dir": str(run_dir),
        "run_id": run_dir.name,
        "summary": load_json_if_exists(run_dir / "summary.json"),
        "condition_summary": load_json_if_exists(run_dir / "condition_summary.json"),
        "ragas_summary": load_json_if_exists(run_dir / "ragas_summary.json"),
        "ragas_per_sample": load_json_if_exists(run_dir / "ragas_per_sample.json"),
    }


@app.post("/eval/run_ragas")
def run_ragas_eval():
    run_dir = latest_eval_run_dir()
    if run_dir is None:
        raise HTTPException(status_code=404, detail="No evaluation runs found")

    cmd = [
        sys.executable,
        str(BACKEND_DIR / "eval" / "ragas_eval.py"),
        str(run_dir),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(BACKEND_DIR.parent),
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail=f"RAGAS evaluation timed out: {exc}") from exc

    if proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "RAGAS evaluation failed",
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-4000:],
            },
        )

    return {
        "status": "ok",
        "run_dir": str(run_dir),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "ragas_summary": load_json_if_exists(run_dir / "ragas_summary.json"),
    }
