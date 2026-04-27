"""
Fill the official 5E character sheet PDF using page-aware field mapping.
"""

from typing import Any, Dict
from pathlib import Path
import re
import io

from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import NameObject

from rules_data import ABILITIES, CLASS_RULES, SKILL_TO_ABILITY, ability_mod, canonical_class_key, prof_bonus

PDF_TEMPLATE = Path(__file__).resolve().parent / "data" / "pdf" / "5E_CharacterSheet_Fillable.pdf"


def _compact_text(value: Any, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_chars:
        return text
    clipped = text[: max_chars - 3].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped + "..."


def _join_lines(items: list[str], max_chars: int) -> str:
    text = "\n".join(item for item in items if item)
    return _compact_text(text, max_chars)


def _first_sentence(value: Any, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    return _compact_text(parts[0], max_chars)


def fill_pdf(sheet_json: Dict[str, Any]) -> bytes:
    if not PDF_TEMPLATE.exists():
        raise FileNotFoundError(f"PDF template not found at {PDF_TEMPLATE}")

    reader = PdfReader(str(PDF_TEMPLATE))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)

    field_pages = {}
    field_annots = {}
    for page_index, page in enumerate(writer.pages):
        annots = page.get("/Annots", [])
        if hasattr(annots, "get_object"):
            annots = annots.get_object()
        for annot_ref in annots or []:
            annot = annot_ref.get_object()
            name = annot.get("/T")
            if name:
                field_pages.setdefault(str(name), []).append(page_index)
                field_annots.setdefault(str(name), []).append(annot)

    def page_indices(name: str):
        return field_pages.get(name, [])

    def set_field(name: str, value: Any):
        for page_index in page_indices(name):
            writer.update_page_form_field_values(
                writer.pages[page_index],
                {name: str(value) if value is not None else ""},
            )

    def spell_field_sections():
        spell_fields = []
        for name, annots in field_annots.items():
            if not str(name).startswith("Spells "):
                continue
            annot = annots[0]
            rect = annot.get("/Rect")
            if rect:
                spell_fields.append((str(name), float(rect[0]), float(rect[1])))

        cols = {}
        for name, x, y in spell_fields:
            cols.setdefault(round(x), []).append((y, name))

        left_top = [name for y, name in sorted(cols.get(40, []), reverse=True)]
        left_all = [name for y, name in sorted(cols.get(41, []), reverse=True)]
        mid_all = [name for y, name in sorted(cols.get(230, []), reverse=True)]
        right_all = [name for y, name in sorted(cols.get(417, []), reverse=True)]

        return {
            "cantrip": left_top,
            "1": left_all[:12],
            "2": left_all[12:],
            "3": mid_all[:13],
            "4": mid_all[13:26],
            "5": mid_all[26:],
            "6": right_all[:9],
            "7": right_all[9:18],
            "8": right_all[18:25],
            "9": right_all[25:],
        }

    def spell_checkbox_sections():
        checkbox_fields = []
        for name, annots in field_annots.items():
            if not str(name).startswith("Check Box"):
                continue
            annot = annots[0]
            rect = annot.get("/Rect")
            if rect and float(rect[0]) < 450 and float(rect[1]) < 430:
                checkbox_fields.append((str(name), float(rect[0]), float(rect[1])))

        cols = {}
        for name, x, y in checkbox_fields:
            cols.setdefault(round(x), []).append((y, name))

        left_all = [name for y, name in sorted(cols.get(32, []), reverse=True)]
        mid_all = [name for y, name in sorted(cols.get(221, []), reverse=True)]
        right_all = [name for y, name in sorted(cols.get(409, []), reverse=True)]

        return {
            "1": left_all[:12],
            "2": left_all[12:],
            "3": mid_all[:13],
            "4": mid_all[13:26],
            "5": mid_all[26:],
            "6": right_all[:9],
            "7": right_all[9:18],
            "8": right_all[18:25],
            "9": right_all[25:],
        }

    def check_box(name: str, on: bool):
        state = NameObject("/Yes" if on else "/Off")
        for annot in field_annots.get(name, []):
            annot.update({
                NameObject("/V"): state,
                NameObject("/AS"): state,
            })

    def score_mod(score: Any) -> str:
        try:
            return f"{ability_mod(int(score)):+d}"
        except Exception:
            return ""

    abilities = sheet_json.get("abilities", {}) or {}
    class_name = sheet_json.get("class", "")
    subclass = sheet_json.get("subclass", "")
    class_level = f"{class_name}".strip()
    if subclass:
        class_level += f" ({subclass})"
    if sheet_json.get("level"):
        class_level += f" {sheet_json.get('level')}"
    class_level = _compact_text(class_level, 28)

    def dedupe(items):
        out = []
        seen = set()
        for item in items:
            text = str(item).strip()
            key = text.lower()
            if text and key not in seen:
                seen.add(key)
                out.append(text)
        return out

    weapon_profs = dedupe(sheet_json.get("weapon_proficiencies") or [])
    armor_profs = dedupe(sheet_json.get("armor_proficiencies") or [])
    misc_profs = dedupe(sheet_json.get("proficiencies") or [])
    languages = dedupe(sheet_json.get("languages") or [])

    prof_lines = []
    if armor_profs:
        prof_lines.append(f"Armor: {', '.join(armor_profs)}")
    if weapon_profs:
        prof_lines.append(f"Weapons: {', '.join(weapon_profs)}")
    if misc_profs:
        prof_lines.append(f"Other: {', '.join(misc_profs)}")
    if languages:
        prof_lines.append(f"Languages: {', '.join(languages)}")

    set_field("CharacterName", _compact_text(sheet_json.get("name", ""), 28))
    set_field("CharacterName 2", _compact_text(sheet_json.get("name", ""), 28))
    set_field("Race ", _compact_text(sheet_json.get("race", ""), 18))
    set_field("Alignment", _compact_text(sheet_json.get("alignment", ""), 18))
    set_field("Background", _compact_text(sheet_json.get("background", ""), 18))
    set_field("ClassLevel", class_level.strip())
    set_field("Age", _compact_text(sheet_json.get("age_group", ""), 12))

    for ability in ABILITIES:
        lower = ability.lower()
        set_field(ability, abilities.get(lower, ""))
    set_field("STRmod", score_mod(abilities.get("str")))
    set_field("DEXmod ", score_mod(abilities.get("dex")))
    set_field("CONmod", score_mod(abilities.get("con")))
    set_field("INTmod", score_mod(abilities.get("int")))
    set_field("WISmod", score_mod(abilities.get("wis")))
    set_field("CHamod", score_mod(abilities.get("cha")))

    set_field("HPMax", sheet_json.get("hitPoints", ""))
    set_field("HPCurrent", sheet_json.get("hitPoints", ""))
    set_field("AC", sheet_json.get("armorClass", ""))
    set_field("Speed", sheet_json.get("speed", ""))
    set_field("Initiative", score_mod(abilities.get("dex")))
    set_field("ProfBonus", f"+{prof_bonus(int(sheet_json.get('level') or 1))}")
    class_key = canonical_class_key(sheet_json.get("class", ""))
    hit_die = (CLASS_RULES.get(class_key) or {}).get("hit_die")
    level = sheet_json.get("level") or ""
    if hit_die and level:
        set_field("HDTotal", level)
        set_field("HD", f"d{hit_die}")

    save_check_map = {
        "STR": "Check Box 11",
        "DEX": "Check Box 18",
        "CON": "Check Box 19",
        "INT": "Check Box 20",
        "WIS": "Check Box 21",
        "CHA": "Check Box 22",
    }
    saves = sheet_json.get("saving_throws") or {}
    for ability in ABILITIES:
        label = {
            "STR": "ST Strength",
            "DEX": "ST Dexterity",
            "CON": "ST Constitution",
            "INT": "ST Intelligence",
            "WIS": "ST Wisdom",
            "CHA": "ST Charisma",
        }[ability]
        set_field(label, saves.get(ability, ""))
        check_box(save_check_map[ability], ability in set(sheet_json.get("saving_throw_proficiencies") or []))

    skill_check_order = [
        "acrobatics",
        "animal",
        "arcana",
        "athletics",
        "deception",
        "history",
        "insight",
        "intimidation",
        "investigation",
        "medicine",
        "nature",
        "perception",
        "performance",
        "persuasion",
        "religion",
        "sleightofhand",
        "stealth",
        "survival",
    ]
    skill_check_map = {name: f"Check Box {23+i}" for i, name in enumerate(skill_check_order)}
    skill_value_field_map = {
        "acrobatics": "Acrobatics",
        "animal": "Animal",
        "arcana": "Arcana",
        "athletics": "Athletics",
        "deception": "Deception ",
        "history": "History ",
        "insight": "Insight",
        "intimidation": "Intimidation",
        "investigation": "Investigation ",
        "medicine": "Medicine",
        "nature": "Nature",
        "perception": "Perception ",
        "performance": "Performance",
        "persuasion": "Persuasion",
        "religion": "Religion",
        "sleightofhand": "SleightofHand",
        "stealth": "Stealth ",
        "survival": "Survival",
    }
    skills = sheet_json.get("skills") or {}
    skill_prof_set = {str(value).strip().lower() for value in (sheet_json.get("skill_proficiencies") or [])}
    for skill_name in SKILL_TO_ABILITY:
        field_name = skill_value_field_map[skill_name]
        set_field(field_name, skills.get(skill_name, ""))
        check_box(skill_check_map[skill_name], skill_name in skill_prof_set)

    set_field("Passive", sheet_json.get("passive_perception", ""))
    set_field("ProficienciesLang", _join_lines(prof_lines, 260))
    feature_lines = list(sheet_json.get("features", []) or [])
    senses_text = str(sheet_json.get("senses") or "").strip()
    senses_text = re.sub(r",?\s*passive perception\s+\d+", "", senses_text, flags=re.IGNORECASE).strip(" ,")
    if senses_text:
        feature_lines.append(f"Senses: {senses_text}")
    set_field("Features and Traits", _join_lines(feature_lines, 420))
    set_field("Equipment", _join_lines(list(sheet_json.get("equipment", []) or []), 260))
    notes_text = _compact_text(sheet_json.get("notes", ""), 240)
    short_notes = _first_sentence(sheet_json.get("notes", ""), 110)
    set_field("Backstory", notes_text)

    attacks = sheet_json.get("attacks") or []
    attack_names = [attack.get("name", "") for attack in attacks[:3]]
    while len(attack_names) < 3:
        attack_names.append("")
    set_field("Wpn Name", attack_names[0])
    set_field("Wpn Name 2", attack_names[1])
    set_field("Wpn Name 3", attack_names[2])

    attack_lines = []
    for attack in attacks[:3]:
        line = attack.get("name", "")
        if attack.get("attack_bonus") is not None:
            line += f" +{attack.get('attack_bonus')}"
        if attack.get("damage"):
            line += f" ({attack.get('damage')})"
        attack_lines.append(line)
    set_field("AttacksSpellcasting", "\n".join(attack_lines))

    spell_lines = []
    for level_key, names in (sheet_json.get("spells") or {}).items():
        label = "Cantrips" if str(level_key).lower() in {"0", "cantrip", "cantrips"} else f"Level {level_key}"
        spell_lines.append(f"{label}: {', '.join(names)}")
    if spell_lines:
        set_field("Feat+Traits", _join_lines(spell_lines, 320))

    if sheet_json.get("spellcasting_ability"):
        set_field("Spellcasting Class 2", class_name)
        set_field("SpellcastingAbility 2", sheet_json.get("spellcasting_ability"))
        set_field("SpellSaveDC  2", sheet_json.get("spell_save_dc", ""))
        set_field("SpellAtkBonus 2", f"+{sheet_json.get('spell_attack_bonus')}" if sheet_json.get("spell_attack_bonus") is not None else "")

        sections = spell_field_sections()
        checkbox_sections = spell_checkbox_sections()
        prepared_rule = ((sheet_json.get("spell_capacity") or {}).get("rule") or "").startswith("prepared")
        for bucket, field_names in sections.items():
            names = (sheet_json.get("spells") or {}).get(bucket) or []
            for field_name, spell_name in zip(field_names, names):
                set_field(field_name, spell_name)
            if prepared_rule and bucket in checkbox_sections:
                for checkbox_name in checkbox_sections[bucket][: len(names)]:
                    check_box(checkbox_name, True)

    set_field("PersonalityTraits ", short_notes)
    set_field("Ideals", _compact_text(sheet_json.get("alignment", ""), 40))
    set_field("Bonds", _compact_text(sheet_json.get("background", ""), 40))
    set_field("Flaws", "")

    writer.set_need_appearances_writer()

    bio = io.BytesIO()
    writer.write(bio)
    return bio.getvalue()
