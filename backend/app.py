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
import requests
from fill_pdf import fill_pdf

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

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


class GenerateRequest(BaseModel):
    entity_type: str = "character"          # "character" | "enemy" | "npc"
    roll_mode: str                           # "auto" | "standard_array" | "manual"
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


ABILITY_KEYS = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]


def normalize_roll_inputs(req: GenerateRequest) -> None:
    """Validate and normalize roll inputs so all roll modes behave consistently."""
    mode = (req.roll_mode or "auto").strip().lower()
    if mode not in {"auto", "standard_array", "manual"}:
        raise HTTPException(status_code=400, detail="roll_mode must be one of auto, standard_array, manual")

    def parse_int_list(values: Optional[List[int]]) -> List[int]:
        out: List[int] = []
        for v in values or []:
            try:
                out.append(int(v))
            except Exception:
                raise HTTPException(status_code=400, detail="manual_rolls must contain integers")
        return out

    def parse_assignment(values: Optional[Dict[str, int]]) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for k, v in (values or {}).items():
            key = str(k).strip().upper()
            if key not in ABILITY_KEYS:
                raise HTTPException(status_code=400, detail=f"ability_assignment contains invalid ability key: {k}")
            try:
                out[key] = int(v)
            except Exception:
                raise HTTPException(status_code=400, detail=f"ability_assignment value for {k} must be an integer")
        return out

    req.roll_mode = mode

    if mode == "auto":
        req.manual_rolls = None
        req.ability_assignment = None
        return

    if mode == "standard_array":
        assignment = parse_assignment(req.ability_assignment)
        if assignment:
            if set(assignment.keys()) != set(ABILITY_KEYS):
                raise HTTPException(status_code=400, detail="ability_assignment must include all six abilities for standard_array")
            if sorted(assignment.values()) != sorted(STANDARD_ARRAY):
                raise HTTPException(status_code=400, detail="ability_assignment must use standard array values only")
            req.ability_assignment = assignment
        else:
            req.ability_assignment = None
        req.manual_rolls = STANDARD_ARRAY.copy()
        return

    # manual mode
    rolls = parse_int_list(req.manual_rolls)
    if len(rolls) != 6:
        raise HTTPException(status_code=400, detail="manual_rolls must contain exactly 6 values for manual mode")
    if any(v < 3 or v > 18 for v in rolls):
        raise HTTPException(status_code=400, detail="manual_rolls values must be between 3 and 18")

    assignment = parse_assignment(req.ability_assignment)
    if assignment:
        if set(assignment.keys()) != set(ABILITY_KEYS):
            raise HTTPException(status_code=400, detail="ability_assignment must include all six abilities for manual mode")
        if sorted(assignment.values()) != sorted(rolls):
            raise HTTPException(status_code=400, detail="ability_assignment values must exactly match manual_rolls")
        req.ability_assignment = assignment
    else:
        # Deterministic fallback: assign in STR..CHA order
        req.ability_assignment = {ability: rolls[i] for i, ability in enumerate(ABILITY_KEYS)}
    req.manual_rolls = rolls


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
    elif req.roll_mode == "manual" and req.manual_rolls:
        question += f" Use these rolled scores {req.manual_rolls} for abilities."
        if req.ability_assignment:
            question += f" Apply this assignment: {req.ability_assignment}."
    else:
        question += " Roll suitable ability scores automatically (4d6 drop lowest style) and assign logically."

    question += " Respect the 5e rules in the provided context."

    return question


@app.post("/generate_character")
def generate_character(req: GenerateRequest):
    normalize_roll_inputs(req)
    question = build_question(req)

    # Retrieve context from index (may be empty if index failed to load)
    nodes = retriever.retrieve(question)
    context_parts = []
    for i, n in enumerate(nodes, start=1):
        try:
            text = n.get_content()
        except AttributeError:
            text = getattr(n.node, "text", "")
        context_parts.append(f"--- Source {i} ---\n{text.strip()}")

    context = "\n\n".join(context_parts)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a Dungeons and Dragons 5e builder. Use only the provided context (PHB and related books). "
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
                "  \"short_blurb\": \"2-3 sentences of character building linking age, race, class, subclass, background, through a short description.\"\n"
                "}\n"
                "- stats must be an object with STR, DEX, CON, INT, WIS, CHA integers (not strings).\n"
                "- hp, ac, speed, level must be integers (not strings).\n"
                "- Use a SINGLE class unless the user explicitly requests multiclass; otherwise choose one class/subclass that fits and matches the given race/background/alignment and concept (avoid defaulting to wizard or repeating the example). Never leave example placeholders in the final JSON.\n"
                "- If level allows feats or ASIs and choices are implied or necessary, add them to the features array (include the feat names or note \"ASI\" with the adjusted scores).\n"
                "- Prefer backgrounds, languages, spells, and gear found in the provided context/books.\n"
                "- Spells must be appropriate for class, race, and level. Do not exceed the maximum spell level for the class at the given level. Include a sensible number of cantrips and known/prepared spells for that class.\n"
                "- If entity_type is NPC, still fill the schema with NPC-appropriate class/background. If enemy, use class='enemy' and subclass as creature type and fill stats similarly.\n"
                "Respond with JSON only, no commentary."
            ),
        },
        {
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion: {question}",
        },
    ]

    import json
    import re

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

    def parse_json_or_fallback(raw_text: str) -> dict:
        parsed_obj = None
        try:
            parsed_obj = json.loads(raw_text)
        except Exception:
            # try to extract first JSON object from the text
            m = re.search(r"\{.*", raw_text, re.S)
            if m:
                candidate = longest_balanced_prefix(m.group(0))
                try:
                    parsed_obj = json.loads(candidate)
                except Exception:
                    parsed_obj = None
        if isinstance(parsed_obj, dict):
            return parsed_obj
        # fallback: extract key fields with regex even if JSON malformed
        def grab(key, default=None):
            m = re.search(rf'"{key}"\s*:\s*"([^"]+)"', raw_text, re.I)
            return m.group(1) if m else default

        def grab_int(key, default=None):
            m = re.search(rf'"{key}"\s*:\s*([0-9]+)', raw_text, re.I)
            return int(m.group(1)) if m else default

        stats_obj = {}
        for k in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
            stats_obj[k] = grab_int(k)
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

    def is_placeholder_text(value) -> bool:
        if not isinstance(value, str):
            return True
        lowered = value.strip().lower()
        return lowered in {"", "unspecified", "none", "null", "tbd", "n/a", "unknown"}

    def coerce_int(val):
        try:
            return int(val)
        except Exception:
            return None

    class_display = {
        "barbarian": "Barbarian",
        "bard": "Bard",
        "cleric": "Cleric",
        "druid": "Druid",
        "fighter": "Fighter",
        "monk": "Monk",
        "paladin": "Paladin",
        "ranger": "Ranger",
        "rogue": "Rogue",
        "sorcerer": "Sorcerer",
        "warlock": "Warlock",
        "wizard": "Wizard",
        "artificer": "Artificer",
    }

    default_subclass = {
        "barbarian": "Path of the Berserker",
        "bard": "College of Lore",
        "cleric": "Life Domain",
        "druid": "Circle of the Land",
        "fighter": "Battle Master",
        "monk": "Way of the Open Hand",
        "paladin": "Oath of Devotion",
        "ranger": "Hunter",
        "rogue": "Thief",
        "sorcerer": "Draconic Bloodline",
        "warlock": "The Fiend",
        "wizard": "School of Evocation",
        "artificer": "Alchemist",
    }

    def class_key_from_text(value: Optional[str]) -> str:
        text = (value or "").strip().lower()
        for key in class_display:
            if key in text:
                return key
        return ""

    def choose_class_from_stats(stats_data: dict) -> str:
        values = {}
        for abil in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
            values[abil] = coerce_int(stats_data.get(abil)) or 10
        dominant = max(values, key=values.get)
        if dominant == "INT":
            return "wizard"
        if dominant == "CHA":
            return "bard"
        if dominant == "WIS":
            return "cleric"
        if dominant == "STR":
            return "fighter"
        if dominant == "DEX":
            return "rogue"
        return "fighter"

    alignment_map = {
        "LG": "Lawful Good",
        "NG": "Neutral Good",
        "CG": "Chaotic Good",
        "LN": "Lawful Neutral",
        "TN": "True Neutral",
        "CN": "Chaotic Neutral",
        "LE": "Lawful Evil",
        "NE": "Neutral Evil",
        "CE": "Chaotic Evil",
    }

    def normalize_alignment(value: Optional[str]) -> str:
        if not value:
            return "Unspecified"
        trimmed = value.strip()
        if len(trimmed) <= 2:
            mapped = alignment_map.get(trimmed.upper())
            if mapped:
                return mapped
        # If it already looks like full words, keep it.
        return trimmed

    def max_spell_level_for_class(class_key: str, level: int) -> int:
        if class_key in {"paladin", "ranger"}:
            if level < 2:
                return 0
            if level <= 4:
                return 1
            if level <= 8:
                return 2
            if level <= 12:
                return 3
            if level <= 16:
                return 4
            return 5
        if class_key == "artificer":
            if level <= 4:
                return 1
            if level <= 8:
                return 2
            if level <= 12:
                return 3
            if level <= 16:
                return 4
            return 5
        if class_key == "warlock":
            if level <= 2:
                return 1
            if level <= 4:
                return 2
            if level <= 6:
                return 3
            if level <= 8:
                return 4
            return 5
        # full casters
        if level <= 2:
            return 1
        if level <= 4:
            return 2
        if level <= 6:
            return 3
        if level <= 8:
            return 4
        if level <= 10:
            return 5
        if level <= 12:
            return 6
        if level <= 14:
            return 7
        if level <= 16:
            return 8
        return 9

    def cantrips_known_for(class_key: str, level: int) -> int:
        tables = {
            "bard": [2, 2, 2, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
            "cleric": [3, 3, 3, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5],
            "druid": [2, 2, 2, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
            "sorcerer": [4, 4, 4, 5, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6],
            "warlock": [2, 2, 2, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
            "wizard": [3, 3, 3, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5],
            "artificer": [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
        }
        table = tables.get(class_key)
        if not table:
            return 0
        return table[max(0, min(level, 20)) - 1]

    def spells_known_for(class_key: str, level: int) -> int:
        tables = {
            "bard": [4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 15, 16, 18, 19, 19, 20, 22, 22, 22],
            "sorcerer": [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 12, 13, 13, 14, 14, 15, 15, 15, 15],
            "warlock": [2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 6, 7, 7, 7, 8, 8],
            "ranger": [0, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11],
        }
        table = tables.get(class_key)
        if not table:
            return 0
        return table[max(0, min(level, 20)) - 1]

    def spells_prepared_for(class_key: str, level: int, stats: dict) -> int:
        if class_key not in {"cleric", "druid", "wizard", "paladin", "artificer"}:
            return 0
        if class_key == "paladin" and level < 2:
            return 0
        ability = "WIS"
        if class_key in {"wizard", "artificer"}:
            ability = "INT"
        if class_key == "paladin":
            ability = "CHA"
        mod_val = (stats.get(ability, 10) - 10) // 2
        if class_key in {"paladin", "artificer"}:
            base = max(1, level // 2)
        else:
            base = level
        return max(1, base + mod_val)

    def wizard_spellbook_total(level: int) -> int:
        return 6 + max(level - 1, 0) * 2

    SPELL_CACHE_PATH = "/private/tmp/cc_open5e_spells.json"

    def fetch_open5e_spells() -> List[dict]:
        try:
            if os.path.exists(SPELL_CACHE_PATH):
                with open(SPELL_CACHE_PATH, "r", encoding="utf-8") as fh:
                    return json.load(fh)
        except Exception:
            pass
        spells: List[dict] = []
        url = "https://api.open5e.com/spells/?limit=200"
        try:
            while url:
                resp = requests.get(url, timeout=12)
                resp.raise_for_status()
                data = resp.json()
                spells.extend(data.get("results", []))
                url = data.get("next")
        except Exception as exc:
            logger.warning("Failed to fetch Open5e spells: %s", exc)
            return []
        try:
            with open(SPELL_CACHE_PATH, "w", encoding="utf-8") as fh:
                json.dump(spells, fh)
        except Exception:
            pass
        return spells

    def extract_spell_classes(spell: dict) -> List[str]:
        for key in ["spell_lists", "spell_list", "classes", "class_list", "dnd_class"]:
            val = spell.get(key)
            if not val:
                continue
            if isinstance(val, list):
                out = []
                for item in val:
                    if isinstance(item, str):
                        out.append(item)
                    elif isinstance(item, dict) and "name" in item:
                        out.append(item["name"])
                return [x.strip().lower() for x in out if str(x).strip()]
            if isinstance(val, str):
                return [x.strip().lower() for x in val.split(",") if x.strip()]
        return []

    def class_spell_pool(class_key: str, max_level: int) -> List[dict]:
        spells = fetch_open5e_spells()
        if not spells:
            return []
        # Prefer SRD if available
        srd_spells = [s for s in spells if s.get("document__slug") in {"wotc-srd", "srd"}]
        pool = srd_spells if srd_spells else spells
        out = []
        for spell in pool:
            try:
                level_val = int(spell.get("level", 0))
            except Exception:
                level_val = 0
            if level_val > max_level:
                continue
            classes = extract_spell_classes(spell)
            if class_key in classes:
                out.append(spell)
        return out

    def normalise_spells_for_class(spells_obj: dict, class_key: str, level: int, stats: dict) -> Tuple[dict, dict]:
        max_level = max_spell_level_for_class(class_key, level)
        if max_level == 0:
            return {}, {
                "max_spell_level": 0,
                "cantrips_expected": 0,
                "spells_known_expected": 0,
                "spells_prepared_expected": 0,
                "wizard_spellbook_total": 0,
            }
        cantrips_needed = cantrips_known_for(class_key, level)
        known_needed = spells_known_for(class_key, level)
        prepared_needed = spells_prepared_for(class_key, level, stats)
        spellbook_total = wizard_spellbook_total(level) if class_key == "wizard" else 0

        pool = class_spell_pool(class_key, max_level)
        if not pool:
            return spells_obj if isinstance(spells_obj, dict) else {}, {
                "max_spell_level": max_level,
                "cantrips_expected": cantrips_needed,
                "spells_known_expected": known_needed,
                "spells_prepared_expected": prepared_needed,
                "wizard_spellbook_total": spellbook_total,
                "source": "model",
            }
        pool_by_level: Dict[int, List[str]] = {}
        for spell in pool:
            lvl = int(spell.get("level", 0))
            pool_by_level.setdefault(lvl, []).append(spell.get("name"))

        def pick(levels: List[int], count: int) -> List[str]:
            picks: List[str] = []
            for lvl in levels:
                options = pool_by_level.get(lvl, [])
                random.shuffle(options)
                for name in options:
                    if name not in picks:
                        picks.append(name)
                    if len(picks) >= count:
                        return picks
            return picks

        normalised: Dict[str, List[str]] = {}
        if class_key in {"bard", "cleric", "druid", "sorcerer", "warlock", "wizard", "artificer"}:
            cantrip_list = spells_obj.get("cantrip") if isinstance(spells_obj, dict) else []
            cantrip_list = [c for c in (cantrip_list or []) if isinstance(c, str)]
            if len(cantrip_list) < cantrips_needed:
                cantrip_list.extend(pick([0], cantrips_needed - len(cantrip_list)))
            normalised["cantrip"] = cantrip_list[:cantrips_needed] if cantrips_needed else cantrip_list

        # Determine how many non-cantrip spells to provide
        total_non_cantrip = known_needed or prepared_needed or max(1, level)
        if class_key == "wizard":
            total_non_cantrip = max(total_non_cantrip, spellbook_total)

        # Collect existing spells within allowed levels
        existing: Dict[int, List[str]] = {}
        if isinstance(spells_obj, dict):
            for key, value in spells_obj.items():
                if key == "cantrip":
                    continue
                try:
                    lvl = int(str(key).strip())
                except Exception:
                    continue
                if lvl > max_level:
                    continue
                if isinstance(value, list):
                    existing[lvl] = [v for v in value if isinstance(v, str)]

        flat_existing = [name for lvl in sorted(existing) for name in existing[lvl]]
        needed = max(0, total_non_cantrip - len(flat_existing))

        if needed > 0:
            level_order = list(range(max_level, 0, -1))
            extra = pick(level_order, needed)
            flat_existing.extend(extra)

        # Re-split into spell levels (roughly even, biasing higher levels)
        level_buckets = {lvl: [] for lvl in range(1, max_level + 1)}
        for name in flat_existing:
            for lvl in range(max_level, 0, -1):
                if name in pool_by_level.get(lvl, []):
                    level_buckets[lvl].append(name)
                    break
        for lvl, names in level_buckets.items():
            if names:
                normalised[str(lvl)] = names

        breakdown = {
            "max_spell_level": max_level,
            "cantrips_expected": cantrips_needed,
            "spells_known_expected": known_needed,
            "spells_prepared_expected": prepared_needed,
            "wizard_spellbook_total": spellbook_total,
            "source": "open5e",
        }
        return normalised, breakdown

    def missing_required_fields(parsed_obj: dict) -> list[str]:
        missing = []
        required_text = ["name", "race", "class", "subclass", "background", "alignment", "short_blurb"]
        required_number = ["hp", "ac", "speed", "level"]
        for key in required_text:
            if is_placeholder_text(parsed_obj.get(key)):
                missing.append(key)
        for key in required_number:
            try:
                int(parsed_obj.get(key))
            except Exception:
                missing.append(key)
        stats_obj = parsed_obj.get("stats")
        if not isinstance(stats_obj, dict):
            missing.append("stats")
        else:
            for abil in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
                try:
                    int(stats_obj.get(abil))
                except Exception:
                    missing.append(f"stats.{abil}")
        return missing

    def rules_validation_issues(parsed_obj: dict) -> list[str]:
        issues = []
        stats_obj = parsed_obj.get("stats") if isinstance(parsed_obj.get("stats"), dict) else {}

        def stat(ability: str) -> int:
            try:
                return int(stats_obj.get(ability, 0))
            except Exception:
                return 0

        class_name = str(parsed_obj.get("class") or "").strip().lower()
        requested_class_key = class_key_from_text(req.dnd_class)
        parsed_class_key = class_key_from_text(class_name)
        level_val = coerce_int(parsed_obj.get("level"))
        entity_type = (req.entity_type or "character").strip().lower()

        if entity_type in {"character", "npc"} and parsed_class_key == "":
            issues.append("class")
        if requested_class_key and parsed_class_key and requested_class_key != parsed_class_key:
            issues.append("class_mismatch")

        class_requirements = {
            "barbarian": [{"STR": 13}],
            "bard": [{"CHA": 13}],
            "cleric": [{"WIS": 13}],
            "druid": [{"WIS": 13}],
            "fighter": [{"STR": 13}, {"DEX": 13}],  # allow DEX route
            "monk": [{"DEX": 13, "WIS": 13}],
            "paladin": [{"STR": 13, "CHA": 13}],
            "ranger": [{"DEX": 13, "WIS": 13}],
            "rogue": [{"DEX": 13}],
            "sorcerer": [{"CHA": 13}],
            "warlock": [{"CHA": 13}],
            "wizard": [{"INT": 13}],
            "artificer": [{"INT": 13}],
        }

        for cls, req_sets in class_requirements.items():
            if cls in parsed_class_key:
                valid = False
                for req_set in req_sets:
                    if all(stat(abil) >= minimum for abil, minimum in req_set.items()):
                        valid = True
                        break
                if not valid:
                    issues.append("stats_for_class")
                break

        caster_classes = {"bard", "cleric", "druid", "paladin", "ranger", "sorcerer", "warlock", "wizard", "artificer"}
        spells_obj = parsed_obj.get("spells")
        if level_val and level_val >= 1 and any(c in class_name for c in caster_classes):
            has_spells = isinstance(spells_obj, dict) and any(isinstance(v, list) and len(v) > 0 for v in spells_obj.values())
            if not has_spells:
                issues.append("spells")
            else:
                # Max spell level by class progression (simplified PHB)
                if "warlock" in class_name:
                    max_spell_level = 1 if level_val <= 2 else 2 if level_val <= 4 else 3 if level_val <= 6 else 4 if level_val <= 8 else 5
                elif any(c in class_name for c in ["paladin", "ranger", "artificer"]):
                    if level_val < 2:
                        max_spell_level = 0
                    elif level_val <= 4:
                        max_spell_level = 1
                    elif level_val <= 8:
                        max_spell_level = 2
                    elif level_val <= 12:
                        max_spell_level = 3
                    elif level_val <= 16:
                        max_spell_level = 4
                    else:
                        max_spell_level = 5
                else:
                    # full casters
                    if level_val <= 2:
                        max_spell_level = 1
                    elif level_val <= 4:
                        max_spell_level = 2
                    elif level_val <= 6:
                        max_spell_level = 3
                    elif level_val <= 8:
                        max_spell_level = 4
                    elif level_val <= 10:
                        max_spell_level = 5
                    elif level_val <= 12:
                        max_spell_level = 6
                    elif level_val <= 14:
                        max_spell_level = 7
                    elif level_val <= 16:
                        max_spell_level = 8
                    else:
                        max_spell_level = 9

                # Validate spell levels do not exceed max
                for key, value in spells_obj.items():
                    if key == "cantrip":
                        continue
                    try:
                        lvl = int(str(key).strip())
                    except Exception:
                        continue
                    if lvl > max_spell_level:
                        issues.append("spells_level")
                        break

                # Require at least one cantrip for full casters and warlocks
                if any(c in class_name for c in ["bard", "cleric", "druid", "sorcerer", "warlock", "wizard"]):
                    cantrips = spells_obj.get("cantrip")
                    if not (isinstance(cantrips, list) and len(cantrips) > 0):
                        issues.append("cantrips")

        return issues

    raw = ""
    parsed = {}
    used_model = ""
    for attempt in range(2):
        try:
            raw, used_model = chat_with_fallback(messages)
        except Exception as exc:
            logger.exception("HF chat_completion failed")
            raise HTTPException(
                status_code=502,
                detail=f"Upstream model error: {exc}. Configure HF_MODEL or HF_MODEL_CANDIDATES with supported chat models.",
            )
        parsed = parse_json_or_fallback(raw)
        missing = missing_required_fields(parsed)
        rule_issues = [] if missing else rules_validation_issues(parsed)
        if not missing and not rule_issues:
            break
        if attempt == 0:
            issue_parts = []
            if missing:
                issue_parts.append("missing required fields: " + ", ".join(missing))
            if rule_issues:
                issue_parts.append("rule validation issues: " + ", ".join(rule_issues))
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Regenerate STRICT JSON only. Previous output had "
                        + "; ".join(issue_parts)
                        + ". Ensure all required fields are non-null, typed correctly, and mechanically legal."
                    ),
                }
            )

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

    entity_type = (req.entity_type or "character").strip().lower()
    requested_class_key = class_key_from_text(req.dnd_class)
    parsed_class_key = class_key_from_text(parsed.get("class"))
    if entity_type == "enemy":
        class_key = "enemy"
    elif requested_class_key:
        class_key = requested_class_key
    elif parsed_class_key:
        class_key = parsed_class_key
    else:
        class_key = choose_class_from_stats(stats_norm)

    class_name = "enemy" if class_key == "enemy" else class_display.get(class_key, "Fighter")
    cls_lower = class_name.lower()

    subclass_name = parsed.get("subclass")
    if class_key == "enemy":
        if is_placeholder_text(subclass_name):
            subclass_name = "Humanoid"
    else:
        if is_placeholder_text(subclass_name):
            subclass_name = default_subclass.get(class_key, "Adventurer")

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

    hp = coerce_int(parsed.get("hp")) or 0
    ac = coerce_int(parsed.get("ac")) or 0
    speed = coerce_int(parsed.get("speed")) or 30
    # Default level to a plausible random range if neither the model nor user provided one
    level = coerce_int(parsed.get("level") or req.level)
    if not level:
        level = random.randint(2, 10)
    alignment = normalize_alignment(parsed.get("alignment") or req.alignment)
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

    # Derived numbers
    def mod(score: int) -> int:
        return (score - 10) // 2

    pb = 2 + (level - 1) // 4
    con_mod = mod(stats_norm["CON"])
    dex_mod = mod(stats_norm["DEX"])

    # Hit dice by class (PHB)
    class_hit_die = {
        "barbarian": 12,
        "fighter": 10,
        "paladin": 10,
        "ranger": 10,
        "bard": 8,
        "cleric": 8,
        "druid": 8,
        "monk": 8,
        "rogue": 8,
        "warlock": 8,
        "artificer": 8,
        "sorcerer": 6,
        "wizard": 6,
    }
    hit_die = class_hit_die.get(class_key, 8)
    avg_hit_die = (hit_die // 2) + 1
    hp_calc = max(level, (hit_die + con_mod) + (level - 1) * (avg_hit_die + con_mod))
    if entity_type in {"character", "npc"}:
        hp = hp_calc
    elif hp <= 0:
        hp = hp_calc

    # AC calculation (simple)
    def calc_ac():
        shield_bonus = 2 if any("shield" in item.lower() for item in equipment) else 0
        armor = [e.lower() for e in equipment if any(x in e.lower() for x in ["armor", "mail", "plate", "leather", "breastplate", "chain shirt", "scale", "hide", "ring mail"])]
        # defaults
        base = 10 + dex_mod
        source = "Unarmored"
        # monk/barbarian unarmored
        cls = cls_lower
        if not armor:
            if "monk" in cls:
                base = 10 + dex_mod + mod(stats_norm["WIS"])
                source = "Unarmored Defense (Monk)"
            elif "barbarian" in cls:
                base = 10 + dex_mod + mod(stats_norm["CON"])
                source = "Unarmored Defense (Barbarian)"
        # armor types
        for a in armor:
            if "studded" in a:
                base = 12 + dex_mod
                source = "Studded Leather"
            elif "leather" in a:
                base = 11 + dex_mod
                source = "Leather"
            elif "padded" in a:
                base = 11 + dex_mod
                source = "Padded"
            elif "hide" in a:
                base = 12 + min(dex_mod, 2)
                source = "Hide"
            elif "chain shirt" in a:
                base = 13 + min(dex_mod, 2)
                source = "Chain Shirt"
            elif "scale" in a:
                base = 14 + min(dex_mod, 2)
                source = "Scale Mail"
            elif "breastplate" in a:
                base = 14 + min(dex_mod, 2)
                source = "Breastplate"
            elif "half plate" in a:
                base = 15 + min(dex_mod, 2)
                source = "Half Plate"
            elif "ring mail" in a:
                base = 14
                source = "Ring Mail"
            elif "chain mail" in a:
                base = 16
                source = "Chain Mail"
            elif "splint" in a:
                base = 17
                source = "Splint"
            elif "plate" in a:
                base = 18
                source = "Plate"
        return base + shield_bonus, source, shield_bonus
    ac_calc, ac_source, shield_bonus = calc_ac()
    if entity_type in {"character", "npc"}:
        ac = ac_calc
    elif ac == 0:
        ac = ac_calc

    # Skills and saves
    skill_names = {
        "acrobatics": "DEX",
        "animal": "WIS",
        "athletics": "STR",
        "deception": "CHA",
        "history": "INT",
        "insight": "WIS",
        "intimidation": "CHA",
        "investigation": "INT",
        "nature": "INT",
        "performance": "CHA",
        "medicine": "WIS",
        "religion": "INT",
        "stealth": "DEX",
        "persuasion": "CHA",
        "sleightofhand": "DEX",
        "survival": "WIS",
        "perception": "WIS",
        "arcana": "INT",
    }
    profs_lower = [p.lower() for p in (skill_profs or [])]

    def skill_bonus(skill_key: str):
        abil = skill_names[skill_key]
        val = mod(stats_norm[abil])
        if any(skill_key in p for p in profs_lower):
            val += pb
        return val

    # If model didn't give skill profs, choose sensible defaults per class/background
    class_skill_options = {
        "barbarian": (2, ["animal", "athletics", "intimidation", "nature", "perception", "survival"]),
        "bard": (3, list(skill_names.keys())),  # any 3
        "cleric": (2, ["history", "insight", "medicine", "persuasion", "religion"]),
        "druid": (2, ["arcana", "animal", "insight", "medicine", "nature", "perception", "religion", "survival"]),
        "fighter": (2, ["acrobatics", "animal", "athletics", "history", "insight", "intimidation", "perception", "survival"]),
        "monk": (2, ["acrobatics", "athletics", "history", "insight", "religion", "stealth"]),
        "paladin": (2, ["athletics", "insight", "intimidation", "medicine", "persuasion", "religion"]),
        "ranger": (3, ["animal", "athletics", "insight", "investigation", "nature", "perception", "stealth", "survival"]),
        "rogue": (4, ["acrobatics", "athletics", "deception", "insight", "intimidation", "investigation", "perception", "performance", "persuasion", "sleightofhand", "stealth"]),
        "sorcerer": (2, ["arcana", "deception", "insight", "intimidation", "persuasion", "religion"]),
        "warlock": (2, ["arcana", "deception", "history", "intimidation", "investigation", "nature", "religion"]),
        "wizard": (2, ["arcana", "history", "insight", "investigation", "medicine", "religion"]),
        "artificer": (2, ["arcana", "history", "investigation", "medicine", "nature", "perception", "sleightofhand"]),
    }
    if not skill_profs:
        for cls, (n, opts) in class_skill_options.items():
            if cls in cls_lower:
                skill_profs = random.sample(opts, min(n, len(opts)))
                profs_lower = [p.lower() for p in skill_profs]
                break

    skills = {k: skill_bonus(k) for k in skill_names}
    passive_perception = 10 + skills["perception"]

    # Saving throws proficiency by class
    class_save_profs = {
        "barbarian": {"STR", "CON"},
        "bard": {"DEX", "CHA"},
        "cleric": {"WIS", "CHA"},
        "druid": {"INT", "WIS"},
        "fighter": {"STR", "CON"},
        "monk": {"STR", "DEX"},
        "paladin": {"WIS", "CHA"},
        "ranger": {"STR", "DEX"},
        "rogue": {"DEX", "INT"},
        "sorcerer": {"CON", "CHA"},
        "warlock": {"WIS", "CHA"},
        "wizard": {"INT", "WIS"},
        "artificer": {"CON", "INT"},
    }
    cls_lower = (parsed.get("class") or "").lower()
    save_profs = set(s.upper() for s in saving_throw_profs) if saving_throw_profs else set()
    if not save_profs:
        for cls, saves in class_save_profs.items():
            if cls in cls_lower:
                save_profs = saves
                break
    saving_throw_profs = list(save_profs)
    saving_throws = {}
    for abil in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
        val = mod(stats_norm[abil])
        if abil in save_profs:
            val += pb
        saving_throws[abil] = val

    # Spellcasting stats
    spellcasting_classes = {
        "bard": "CHA",
        "cleric": "WIS",
        "druid": "WIS",
        "paladin": "CHA",
        "ranger": "WIS",
        "sorcerer": "CHA",
        "warlock": "CHA",
        "wizard": "INT",
        "artificer": "INT",
    }
    spell_ability = None
    for cls, abil in spellcasting_classes.items():
        if cls in cls_lower:
            spell_ability = abil
            break
    spell_save_dc = None
    spell_attack_bonus = None
    if spell_ability:
        spell_mod = mod(stats_norm[spell_ability])
        spell_save_dc = 8 + pb + spell_mod
        spell_attack_bonus = pb + spell_mod

    spells_breakdown = None
    if class_key in {"bard", "cleric", "druid", "sorcerer", "warlock", "wizard", "artificer", "paladin", "ranger"} and level >= 1:
        try:
            spells, spells_breakdown = normalise_spells_for_class(spells, class_key, level, stats_norm)
        except Exception as exc:
            logger.warning("Spell normalization failed: %s", exc)

    calc_breakdown = {
        "proficiency_bonus": {
            "formula": f"2 + floor((level-1)/4) = {pb}",
            "level": level,
            "result": pb,
        },
        "hp": {
            "formula": f"{hit_die}+{con_mod} + (level-1)*({avg_hit_die}+{con_mod})",
            "hit_die": hit_die,
            "con_mod": con_mod,
            "level": level,
            "result": hp,
        },
        "ac": {
            "formula": f"{ac_source} base + DEX({dex_mod}) + Shield({shield_bonus})",
            "armor": ac_source,
            "dex_mod": dex_mod,
            "shield_bonus": shield_bonus,
            "result": ac,
        },
    }
    if spell_ability:
        spell_mod = mod(stats_norm[spell_ability])
        calc_breakdown["spellcasting"] = {
            "ability": spell_ability,
            "ability_mod": spell_mod,
            "spell_save_dc": spell_save_dc,
            "spell_attack_bonus": spell_attack_bonus,
            "formula": f"DC 8 + PB({pb}) + {spell_ability}({spell_mod}); attack PB({pb}) + {spell_ability}({spell_mod})",
        }
    if spells_breakdown:
        calc_breakdown["spells"] = spells_breakdown

    # Apply saving throw profs from JSON if provided
    if saving_throw_profs:
        save_profs = {s.upper() for s in saving_throw_profs}
        for abil in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
            val = mod(stats_norm[abil])
            if abil in save_profs:
                val += pb
            saving_throws[abil] = val

    sheet_json = {
        "name": parsed.get("name"),
        "class": class_name,
        "subclass": subclass_name,
        "level": level,
        "race": race,
        "background": background,
        "alignment": alignment,
        "hitPoints": hp,
        "armorClass": ac,
        "speed": speed,
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
        "attacks": attacks,
        "spells": spells,
        "calc_breakdown": calc_breakdown,
    }

    return {
        "question": question,
        "answer": raw,
        "parsed": sheet_json,  # normalized values for UI
        "sheet_json": sheet_json,
        "calc_breakdown": calc_breakdown,
    }


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
        "index_loaded": not isinstance(retriever, type(lambda: None)) and retriever is not None,
        "model": "HuggingFaceH4/zephyr-7b-beta",
    }
