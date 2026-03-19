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
    dedupe,
    normalize_armor_proficiencies,
    normalize_skill_name,
    normalize_skill_proficiencies,
    normalize_saving_throw_proficiencies,
    normalize_weapon_proficiencies,
    prof_bonus,
    spell_capacity_for_class,
    validate_spells,
)

# Logger setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

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

# Load the serialized index once; if unavailable, keep serving with an empty retriever
try:
    with open("character_index.pkl", "rb") as f:
        index: VectorStoreIndex = pickle.load(f)
    retriever = index.as_retriever(similarity_top_k=5)
except Exception as exc:  # fallback if pickle/device mismatch
    logger.warning("Failed to load character_index.pkl (%s); using empty retriever", exc)

    class _NullRetriever:
        """Stub retriever so the API stays up even without an index."""

        def retrieve(self, _: str):
            return []

    retriever = _NullRetriever()

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
    experimental_mode: str = "rag"          # "no_rag" | "rag" | "validated_iterative_rag"
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
        "  \"level\": 5,  // if user did not give a level, pick a sensible one (default around 3)\n"
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


def collect_validation_issues(parsed: dict, req: GenerateRequest) -> list[str]:
    issues = []
    if not isinstance(parsed, dict):
        return ["response was not a JSON object"]

    for field in ["name", "race", "background", "alignment", "short_blurb"]:
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

    if (req.entity_type or "").lower() == "enemy":
        if not parsed.get("creature_type"):
            issues.append("enemy missing creature_type")
        if not parsed.get("challenge_rating"):
            issues.append("enemy missing challenge_rating")

    if isinstance(parsed.get("short_blurb"), str):
        sentence_count = len([s for s in re.split(r"[.!?]+", parsed["short_blurb"]) if s.strip()])
        if sentence_count < 4:
            issues.append("short_blurb too short")

    class_key = canonical_class_key(parsed.get("class") or req.dnd_class or "")
    race_key = canonical_race_key(parsed.get("race") or req.race or "")
    background_text = parsed.get("background") or ""

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

    if class_key and level_int > 0 and all(ability in stats for ability in ABILITIES):
        ability_mods = {ability: ability_mod(int(stats[ability])) for ability in ABILITIES}
        spell_issues, _, capacity = validate_spells(
            parsed.get("spells") or {},
            class_key,
            level_int,
            ability_mods.get((CLASS_RULES.get(class_key) or {}).get("spellcasting", {}).get("ability", ""), 0),
        )
        issues.extend(spell_issues)
        if capacity["rule"] == "noncaster" and parsed.get("spells"):
            issues.append("noncaster has spell entries")

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
        attempts.append(
            {
                "attempt": attempt,
                "used_model": used_model,
                "validation_issues": validation_issues,
            }
        )

        if mode != "validated_iterative_rag" or not validation_issues:
            break

        validation_feedback = "; ".join(validation_issues)

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

    class_name = parsed.get("class")
    if isinstance(class_name, str) and ("/" in class_name or "(" in class_name) and "multiclass" not in (question.lower()):
        class_name = class_name.split("/")[0].split("(")[0].strip()
    class_key = canonical_class_key(class_name or req.dnd_class or "")
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
        level = random.randint(2, 10)
    alignment = parsed.get("alignment") or req.alignment or "Unspecified"
    gender = parsed.get("gender") or req.gender or "Unspecified"
    age_group = parsed.get("age_group") or req.age_group or "Unspecified"
    background = parsed.get("background") or "Unspecified"
    if (not background) or background.lower() in {"unspecified", "sage"}:
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

    skill_profs, invalid_skill_profs, background_key = normalize_skill_proficiencies(
        skill_profs,
        class_key,
        background,
    )
    profs_lower = [p.lower() for p in skill_profs]

    skills = {k: skill_bonus(k) for k in SKILL_TO_ABILITY}
    passive_perception = 10 + skills["perception"]

    saving_throw_profs, invalid_save_profs = normalize_saving_throw_proficiencies(
        saving_throw_profs,
        class_key,
    )
    save_profs = set(saving_throw_profs)
    saving_throws = {}
    for abil in ABILITIES:
        val = ability_mod(stats_norm[abil])
        if abil in save_profs:
            val += pb
        saving_throws[abil] = val

    race_key = canonical_race_key(race)
    weapon_profs, invalid_weapon_profs = normalize_weapon_proficiencies(weapon_profs, class_key, race_key)
    armor_profs, invalid_armor_profs = normalize_armor_proficiencies(armor_profs, class_key)

    spell_ability = ((CLASS_RULES.get(class_key) or {}).get("spellcasting") or {}).get("ability")
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
    )
    if normalized_spells:
        spells = normalized_spells

    post_validation_issues = dedupe(
        generation["validation_issues"]
        + [f"invalid skill proficiencies: {', '.join(invalid_skill_profs)}"] * bool(invalid_skill_profs)
        + [f"invalid saving throw proficiencies: {', '.join(invalid_save_profs)}"] * bool(invalid_save_profs)
        + [f"invalid weapon proficiencies: {', '.join(map(str, invalid_weapon_profs))}"] * bool(invalid_weapon_profs)
        + [f"invalid armor proficiencies: {', '.join(map(str, invalid_armor_profs))}"] * bool(invalid_armor_profs)
        + spell_issues
    )

    sheet_json = {
        "name": parsed.get("name"),
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
        "creature_type": parsed.get("creature_type"),
        "challenge_rating": parsed.get("challenge_rating"),
        "senses": parsed.get("senses"),
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
        "notes": parsed.get("short_blurb"),
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

    response = {
        "question": question,
        "answer": raw,
        "parsed": sheet_json,  # normalized values for UI
        "sheet_json": sheet_json,
        "used_model": used_model,
        "experimental_mode": generation["experimental_mode"],
        "validation_issues": post_validation_issues,
        "attempt_count": generation["attempt_count"],
        "attempts": generation["attempts"],
        "retrieved_sources": generation["retrieved_sources"],
    }
    if (req.entity_type or "").lower() == "enemy":
        response["stat_block"] = build_stat_block(sheet_json)
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


def build_stat_block(sheet: dict) -> str:
    def mod(score: int) -> str:
        try:
            val = int(score)
        except Exception:
            return "+0"
        return f"{(val - 10) // 2:+d}"

    name = sheet.get("name", "Unknown Creature")
    size = sheet.get("size") or "Medium"
    creature_type = sheet.get("creature_type") or sheet.get("subclass") or sheet.get("class") or "creature"
    alignment = sheet.get("alignment") or "Unaligned"
    ac = sheet.get("armorClass", "—")
    hp = sheet.get("hitPoints", "—")
    speed = sheet.get("speed", "—")

    abilities = sheet.get("abilities", {}) or {}
    abil_line = "  ".join(
        f"{k} {abilities.get(k.lower(), abilities.get(k, '—'))} ({mod(abilities.get(k.lower(), abilities.get(k, 10)))})"
        for k in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
    )

    saving = sheet.get("saving_throw_proficiencies") or []
    skills = sheet.get("skill_proficiencies") or []
    senses = sheet.get("senses") or ""
    languages = sheet.get("languages") or []
    cr = sheet.get("challenge_rating") or ""

    lines = [
        name,
        f"{size} {creature_type}, {alignment}",
        f"Armor Class {ac}",
        f"Hit Points {hp}",
        f"Speed {speed} ft.",
        "",
        abil_line,
        "",
    ]

    if saving:
        lines.append(f"Saving Throws {', '.join(saving)}")
    if skills:
        lines.append(f"Skills {', '.join(skills)}")
    if senses:
        lines.append(f"Senses {senses}")
    if languages:
        lines.append(f"Languages {', '.join(languages)}")
    if cr:
        lines.append(f"Challenge {cr}")

    traits = sheet.get("features") or []
    attacks = sheet.get("attacks") or []
    spells = sheet.get("spells") or {}

    if traits:
        lines.append("")
        lines.append("Traits")
        for t in traits:
            lines.append(f"- {t}")

    if spells:
        lines.append("")
        lines.append("Spellcasting")
        for lvl, names in spells.items():
            label = "Cantrips" if str(lvl).lower() in {"0", "cantrip", "cantrips"} else f"Level {lvl}"
            lines.append(f"{label}: {', '.join(names)}")

    if attacks:
        lines.append("")
        lines.append("Actions")
        for a in attacks:
            name = a.get("name", "Attack")
            bonus = a.get("attack_bonus")
            dmg = a.get("damage")
            parts = [name]
            if bonus is not None:
                parts.append(f"+{bonus}")
            if dmg:
                parts.append(f"({dmg})")
            lines.append("- " + " ".join(parts))

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

    required_keys = ["name", "class", "level", "race", "background", "alignment", "hitPoints", "armorClass", "speed", "abilities"]
    missing = [k for k in required_keys if k not in req.sheet_json]
    if missing:
        raise HTTPException(status_code=400, detail=f"sheet_json missing fields: {missing}")

    try:
        pdf_bytes = build_pdf(req.sheet_json)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF build failed: {exc}")

    from fastapi.responses import Response

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=character_sheet.pdf"},
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
        "index_loaded": retriever is not None,
        "model": HF_MODEL_CANDIDATES[0] if HF_MODEL_CANDIDATES else HF_MODEL,
        "candidate_models": HF_MODEL_CANDIDATES,
    }
