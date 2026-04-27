import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rules_data import (
    compute_armor_class,
    compute_hit_points,
    normalize_skill_proficiencies,
    normalize_saving_throw_proficiencies,
    validate_spells,
)
from fill_pdf import PDF_TEMPLATE, fill_pdf


class RulesValidationTests(unittest.TestCase):
    def test_hit_points_are_deterministic(self):
        hp, provenance = compute_hit_points("wizard", 10, 14, parsed_hp=85)
        self.assertEqual(hp, 62)
        self.assertEqual(provenance["model_hp"], 85)
        self.assertEqual(provenance["hit_die"], "d6")

    def test_armor_class_uses_equipment(self):
        ac, provenance = compute_armor_class(
            "wizard",
            "School of Divination",
            {"STR": 8, "DEX": 14, "CON": 14, "INT": 20, "WIS": 16, "CHA": 12},
            ["Quarterstaff"],
            parsed_ac=18,
        )
        self.assertEqual(ac, 12)
        self.assertEqual(provenance["armor"], "unarmored")

    def test_invalid_skill_proficiencies_are_removed(self):
        normalized, invalid, _ = normalize_skill_proficiencies(
            ["History", "Medicine", "Acrobatics", "Performance"],
            "wizard",
            "Entertainer",
        )
        self.assertIn("performance", normalized)
        self.assertIn("acrobatics", normalized)
        self.assertEqual(invalid, [])
        self.assertLessEqual(len(normalized), 4)

    def test_saving_throw_proficiencies_match_class(self):
        normalized, invalid = normalize_saving_throw_proficiencies(["CHA"], "sorcerer")
        self.assertEqual(normalized, ["CHA", "CON"])
        self.assertEqual(invalid, [])

    def test_spell_validation_catches_invalid_cantrip_and_cross_class_spell(self):
        issues, validated, capacity = validate_spells(
            {"cantrip": ["Cure Wounds", "Mage Hand", "Prestidigitation"], "1": ["Magic Missile", "Shield"]},
            "sorcerer",
            3,
            5,
        )
        joined = " | ".join(issues)
        self.assertIn("spell Cure Wounds not on sorcerer list", joined)
        self.assertEqual(validated["1"], ["Magic Missile", "Shield"])
        self.assertEqual(capacity["max_spell_level"], 2)


@unittest.skipUnless(PDF_TEMPLATE.exists(), "official PDF template not available in workspace")
class PdfFillTests(unittest.TestCase):
    def test_fill_pdf_generates_bytes_for_known_sample(self):
        sample = {
            "name": "Test Wizard",
            "class": "Wizard",
            "subclass": "School of Evocation",
            "level": 5,
            "race": "Elf",
            "background": "Sage",
            "alignment": "Neutral Good",
            "hitPoints": 27,
            "armorClass": 12,
            "speed": 30,
            "abilities": {"str": 8, "dex": 14, "con": 14, "int": 18, "wis": 12, "cha": 10},
            "skill_proficiencies": ["arcana", "history"],
            "saving_throw_proficiencies": ["INT", "WIS"],
            "weapon_proficiencies": ["dagger", "dart", "sling", "quarterstaff", "light crossbow"],
            "armor_proficiencies": [],
            "languages": ["Common", "Elvish"],
            "features": ["Arcane Recovery"],
            "equipment": ["Quarterstaff", "Spellbook"],
            "notes": "A sample character used for PDF regression testing.",
            "skills": {"arcana": 7, "history": 7, "perception": 1},
            "saving_throws": {"INT": 7, "WIS": 4},
            "passive_perception": 11,
            "spellcasting_ability": "INT",
            "spell_save_dc": 15,
            "spell_attack_bonus": 7,
            "attacks": [{"name": "Quarterstaff", "attack_bonus": 2, "damage": "1d6 bludgeoning"}],
            "spells": {"cantrip": ["Mage Hand", "Prestidigitation"], "1": ["Magic Missile", "Shield"]},
        }
        pdf_bytes = fill_pdf(sample)
        self.assertGreater(len(pdf_bytes), 1000)


if __name__ == "__main__":
    unittest.main()
