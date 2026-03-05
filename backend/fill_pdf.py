"""
Utility to fill the official 5E_CharacterSheet_Fillable.pdf using PyPDF2.
This is a minimal mapping from sheet_json keys to PDF form field names.
"""

from typing import Dict, Any
from PyPDF2 import PdfReader, PdfWriter

PDF_TEMPLATE = "data/pdf/5E_CharacterSheet_Fillable.pdf"


def fill_pdf(sheet_json: Dict[str, Any]) -> bytes:
    reader = PdfReader(PDF_TEMPLATE)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    fields = reader.get_fields()

    def set_field(name: str, value: Any):
        if name in fields:
            writer.update_page_form_field_values(writer.pages[0], {name: str(value) if value is not None else ""})

    def check_box(name: str, on: bool):
        if name in fields:
            writer.update_page_form_field_values(writer.pages[0], {name: "Yes" if on else "Off"})

    def mod(score: Any) -> str:
        try:
            s = int(score)
            return f"{(s - 10) // 2:+d}"
        except Exception:
            return ""

    def prof_bonus(level: Any) -> str:
        try:
            lvl = int(level)
            return f"+{2 + (lvl - 1) // 4}"
        except Exception:
            return ""

    # Saving throw proficiencies by class (basic)
    CLASS_SAVE_PROFS = {
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

    # Skill to ability mapping
    SKILL_MAP = {
        "acrobatics": "DEX",
        "animal": "WIS",  # Animal Handling
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

    profs_list = [p.lower() for p in (sheet_json.get("proficiencies") or [])]
    # Derive languages/proficiencies text
    languages = sheet_json.get("languages", []) or []
    prof_lang = "\n".join((sheet_json.get("proficiencies", []) or []) + languages)

    def has_prof(skill_key: str) -> bool:
        return any(skill_key in p for p in profs_list)

    # Determine save profs from class
    class_lower = (sheet_json.get("class") or "").lower()
    save_profs = set()
    for cls, saves in CLASS_SAVE_PROFS.items():
        if cls in class_lower:
            save_profs = saves
            break

    # Basic identity
    set_field("CharacterName", sheet_json.get("name", ""))
    set_field("CharacterName 2", sheet_json.get("name", ""))
    set_field("Race ", sheet_json.get("race", ""))
    set_field("Alignment", sheet_json.get("alignment", ""))
    set_field("Background", sheet_json.get("background", ""))
    class_level = f"{sheet_json.get('class','')}".strip()
    if sheet_json.get("subclass"):
        class_level += f" ({sheet_json.get('subclass')})"
    if sheet_json.get("level"):
        class_level += f" {sheet_json.get('level')}"
    set_field("ClassLevel", class_level.strip())
    set_field("Age", sheet_json.get("age_group", ""))

    # Core stats
    abilities = sheet_json.get("abilities", {}) or {}
    set_field("STR", abilities.get("str", ""))
    set_field("DEX", abilities.get("dex", ""))
    set_field("CON", abilities.get("con", ""))
    set_field("INT", abilities.get("int", ""))
    set_field("WIS", abilities.get("wis", ""))
    set_field("CHA", abilities.get("cha", ""))
    set_field("STRmod", mod(abilities.get("str")))
    set_field("DEXmod ", mod(abilities.get("dex")))
    set_field("CONmod", mod(abilities.get("con")))
    set_field("INTmod", mod(abilities.get("int")))
    set_field("WISmod", mod(abilities.get("wis")))
    set_field("CHamod", mod(abilities.get("cha")))

    # Combat
    set_field("HPMax", sheet_json.get("hitPoints", ""))
    set_field("HPCurrent", sheet_json.get("hitPoints", ""))
    set_field("AC", sheet_json.get("armorClass", ""))
    set_field("Speed", sheet_json.get("speed", ""))
    set_field("Initiative", mod(abilities.get("dex")))
    set_field("ProfBonus", prof_bonus(sheet_json.get("level")))

    # Saving throws
    save_check_map = {
        "STR": "Check Box 12",
        "DEX": "Check Box 13",
        "CON": "Check Box 14",
        "INT": "Check Box 15",
        "WIS": "Check Box 16",
        "CHA": "Check Box 17",
    }

    if sheet_json.get("saving_throws"):
        saves = sheet_json["saving_throws"]
        set_field("ST Strength", saves.get("STR", ""))
        set_field("ST Dexterity", saves.get("DEX", ""))
        set_field("ST Constitution", saves.get("CON", ""))
        set_field("ST Intelligence", saves.get("INT", ""))
        set_field("ST Wisdom", saves.get("WIS", ""))
        set_field("ST Charisma", saves.get("CHA", ""))
        for abil, box in save_check_map.items():
            check_box(box, abil in (sheet_json.get("saving_throw_proficiencies") or []) or saves.get(abil) is not None)
    else:
        def save_val(stat_key: str):
            val = mod(abilities.get(stat_key.lower()))
            if stat_key in save_profs:
                try:
                    bonus = int(prof_bonus(sheet_json.get("level")).replace("+", ""))
                    val_int = int(val) if val not in ("", None) else 0
                    return val_int + bonus
                except Exception:
                    return val
            return val

        set_field("ST Strength", save_val("STR"))
        set_field("ST Dexterity", save_val("DEX"))
        set_field("ST Constitution", save_val("CON"))
        set_field("ST Intelligence", save_val("INT"))
        set_field("ST Wisdom", save_val("WIS"))
        set_field("ST Charisma", save_val("CHA"))
        for abil, box in save_check_map.items():
            check_box(box, abil in save_profs)

    # Skills
    # Map skill checkboxes in PDF order (18–34)
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

    skills_source = sheet_json.get("skills")
    if skills_source:
        for field_name, ability_key in SKILL_MAP.items():
            val = skills_source.get(field_name)
            fname = field_name if field_name != "perception" else "Perception "
            set_field(fname, val if val is not None else "")
            box = skill_check_map.get(field_name)
            if box:
                check_box(box, val is not None)
    else:
        for field_name, ability_key in SKILL_MAP.items():
            value = mod(abilities.get(ability_key.lower()))
            prof = has_prof(field_name)
            if prof:
                try:
                    bonus = int(prof_bonus(sheet_json.get("level")).replace("+", ""))
                    value_int = int(value) if value not in ("", None) else 0
                    value = value_int + bonus
                except Exception:
                    pass
            fname = field_name if field_name != "perception" else "Perception "
            set_field(fname, value)
            box = skill_check_map.get(field_name)
            if box:
                check_box(box, prof)

    # Passive Perception
    if sheet_json.get("passive_perception") is not None:
        set_field("Passive", sheet_json["passive_perception"])
    else:
        try:
            wis_mod = int(mod(abilities.get("wis")))
            passive = 10 + wis_mod + (2 if has_prof("perception") else 0)
            set_field("Passive", passive)
        except Exception:
            pass

    # Proficiencies, features, equipment
    feats = "\n".join(sheet_json.get("features", []) or [])
    equip_list = sheet_json.get("equipment", []) or []
    equip = "\n".join(equip_list)
    set_field("ProficienciesLang", prof_lang)
    set_field("Features and Traits", feats)
    set_field("Equipment", equip)
    set_field("Other Proficiencies", prof_lang)

    # Backstory / flavour
    set_field("Backstory", sheet_json.get("notes", ""))

    # Attacks / spellcasting rows - fill from equipment if weapon-like
    weapon_keywords = ["sword", "axe", "bow", "crossbow", "dagger", "mace", "staff", "spear", "hammer", "maul", "whip", "flail"]
    weapons = [e for e in equip_list if any(k in e.lower() for k in weapon_keywords)]
    if sheet_json.get("attacks"):
        weapons = [a.get("name", "") for a in sheet_json["attacks"]] + weapons
    weapons = weapons[:3] + [""] * max(0, 3 - len(weapons))
    set_field("Wpn Name", weapons[0])
    set_field("Wpn Name 2", weapons[1])
    set_field("Wpn Name 3", weapons[2])
    # Put a combined spell/attack summary into AttacksSpellcasting block
    spell_like = [f for f in sheet_json.get("features", []) or [] if "spell" in f.lower() or "cantrip" in f.lower()]
    attacks_block = []
    # include attack bonuses/damage if provided
    for a in (sheet_json.get("attacks") or [])[:3]:
        line = a.get("name", "")
        if a.get("attack_bonus") is not None:
            line += f" +{a.get('attack_bonus')}"
        if a.get("damage"):
            line += f" ({a.get('damage')})"
        attacks_block.append(line)
    for w in weapons:
        if w and w not in attacks_block:
            attacks_block.append(w)
    attacks_block += spell_like
    set_field("AttacksSpellcasting", "\n".join(attacks_block))

    # Spells page summary
    spell_lines = []
    spells_known = sheet_json.get("spells_known") or []
    spells_prepared = sheet_json.get("spells_prepared") or []
    spellbook = sheet_json.get("spellbook") or []
    if spells_known:
        spell_lines.append(f"Spells Known ({len(spells_known)}): " + ", ".join(spells_known))
    if spells_prepared:
        spell_lines.append(f"Spells Prepared ({len(spells_prepared)}): " + ", ".join(spells_prepared))
    if spellbook:
        spell_lines.append(f"Spellbook ({len(spellbook)}): " + ", ".join(spellbook))

    for lvl, names in (sheet_json.get("spells") or {}).items():
        label = "Cantrips" if str(lvl).lower() in {"0", "cantrip", "cantrips"} else f"Level {lvl}"
        spell_lines.append(f"{label}: " + ", ".join(names))
    if spell_lines:
        set_field("Feat+Traits", "\n".join(spell_lines))

    # Spellcasting header (if caster)
    spellcasting_classes = {"bard": "CHA", "cleric": "WIS", "druid": "WIS", "paladin": "CHA", "ranger": "WIS", "sorcerer": "CHA", "warlock": "CHA", "wizard": "INT", "artificer": "INT"}
    spellcasting_ability = None
    for cls, abil in spellcasting_classes.items():
        if cls in class_lower:
            spellcasting_ability = abil
            break
    if spellcasting_ability:
        set_field("Spellcasting Class", sheet_json.get("class", ""))
        set_field("Spellcasting Ability", spellcasting_ability)
        try:
            mod_val = int(mod(abilities.get(spellcasting_ability.lower())))
            pb = int(prof_bonus(sheet_json.get("level")).replace("+", ""))
            set_field("Spell Save DC", 8 + pb + mod_val)
            set_field("Spell Attack Bonus", pb + mod_val)
        except Exception:
            pass
    # Personality / traits fields
    set_field("PersonalityTraits ", sheet_json.get("notes", ""))
    set_field("Ideals", sheet_json.get("alignment", ""))
    set_field("Bonds", sheet_json.get("background", ""))
    set_field("Flaws", "")

    # Write out
    out = bytes()
    import io

    bio = io.BytesIO()
    writer.write(bio)
    return bio.getvalue()
