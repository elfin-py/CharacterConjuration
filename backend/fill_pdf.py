"""
Fill the official 5E character sheet PDF using page-aware field mapping.
"""

from typing import Any, Dict
from pathlib import Path

from PyPDF2 import PdfReader, PdfWriter

from rules_data import ABILITIES, SKILL_TO_ABILITY, ability_mod, prof_bonus

PDF_TEMPLATE = Path(__file__).resolve().parent / "data" / "pdf" / "5E_CharacterSheet_Fillable.pdf"


def fill_pdf(sheet_json: Dict[str, Any]) -> bytes:
    if not PDF_TEMPLATE.exists():
        raise FileNotFoundError(f"PDF template not found at {PDF_TEMPLATE}")

    reader = PdfReader(str(PDF_TEMPLATE))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)

    field_pages = {}
    for page_index, page in enumerate(reader.pages):
        annots = page.get("/Annots", [])
        if hasattr(annots, "get_object"):
            annots = annots.get_object()
        for annot_ref in annots or []:
            annot = annot_ref.get_object()
            name = annot.get("/T")
            if name:
                field_pages.setdefault(str(name), []).append(page_index)

    def page_indices(name: str):
        return field_pages.get(name, [])

    def set_field(name: str, value: Any):
        for page_index in page_indices(name):
            writer.update_page_form_field_values(
                writer.pages[page_index],
                {name: str(value) if value is not None else ""},
            )

    def check_box(name: str, on: bool):
        for page_index in page_indices(name):
            writer.update_page_form_field_values(
                writer.pages[page_index],
                {name: "Yes" if on else "Off"},
            )

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

    all_proficiencies = []
    for group in [
        sheet_json.get("proficiencies") or [],
        sheet_json.get("skill_proficiencies") or [],
        sheet_json.get("saving_throw_proficiencies") or [],
        sheet_json.get("weapon_proficiencies") or [],
        sheet_json.get("armor_proficiencies") or [],
        sheet_json.get("languages") or [],
    ]:
        for item in group:
            if item not in all_proficiencies:
                all_proficiencies.append(item)

    set_field("CharacterName", sheet_json.get("name", ""))
    set_field("CharacterName 2", sheet_json.get("name", ""))
    set_field("Race ", sheet_json.get("race", ""))
    set_field("Alignment", sheet_json.get("alignment", ""))
    set_field("Background", sheet_json.get("background", ""))
    set_field("ClassLevel", class_level.strip())
    set_field("Age", sheet_json.get("age_group", ""))

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

    save_check_map = {
        "STR": "Check Box 12",
        "DEX": "Check Box 13",
        "CON": "Check Box 14",
        "INT": "Check Box 15",
        "WIS": "Check Box 16",
        "CHA": "Check Box 17",
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
        "nature",
        "performance",
        "medicine",
        "religion",
        "stealth",
        "persuasion",
        "sleightofhand",
        "survival",
        "perception",
    ]
    skill_check_map = {name: f"Check Box {18+i}" for i, name in enumerate(skill_check_order)}
    skills = sheet_json.get("skills") or {}
    skill_prof_set = {str(value).lower() for value in (sheet_json.get("skill_proficiencies") or [])}
    for skill_name in SKILL_TO_ABILITY:
        field_name = skill_name if skill_name != "perception" else "Perception "
        set_field(field_name, skills.get(skill_name, ""))
        check_box(skill_check_map[skill_name], skill_name in skill_prof_set)

    set_field("Passive", sheet_json.get("passive_perception", ""))
    set_field("ProficienciesLang", "\n".join(all_proficiencies))
    set_field("Features and Traits", "\n".join(sheet_json.get("features", []) or []))
    set_field("Equipment", "\n".join(sheet_json.get("equipment", []) or []))
    set_field("Other Proficiencies", "\n".join(all_proficiencies))
    set_field("Backstory", sheet_json.get("notes", ""))

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
        set_field("Feat+Traits", "\n".join(spell_lines))

    if sheet_json.get("spellcasting_ability"):
        set_field("Spellcasting Class", class_name)
        set_field("Spellcasting Ability", sheet_json.get("spellcasting_ability"))
        set_field("Spell Save DC", sheet_json.get("spell_save_dc", ""))
        set_field("Spell Attack Bonus", f"+{sheet_json.get('spell_attack_bonus')}" if sheet_json.get("spell_attack_bonus") is not None else "")

    set_field("PersonalityTraits ", sheet_json.get("notes", ""))
    set_field("Ideals", sheet_json.get("alignment", ""))
    set_field("Bonds", sheet_json.get("background", ""))
    set_field("Flaws", "")

    writer.set_need_appearances_writer()
    import io

    bio = io.BytesIO()
    writer.write(bio)
    return bio.getvalue()
