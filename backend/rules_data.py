import re
import random
from functools import lru_cache
from pathlib import Path

ABILITIES = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]

SKILL_TO_ABILITY = {
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

BACKGROUND_SKILLS = {
    "acolyte": ["insight", "religion"],
    "criminal": ["deception", "stealth"],
    "folk hero": ["animal", "survival"],
    "noble": ["history", "persuasion"],
    "sage": ["arcana", "history"],
    "soldier": ["athletics", "intimidation"],
    "urchin": ["sleightofhand", "stealth"],
    "outlander": ["athletics", "survival"],
    "entertainer": ["acrobatics", "performance"],
    "guild artisan": ["insight", "persuasion"],
    "sailor": ["athletics", "perception"],
    "hermit": ["medicine", "religion"],
    "city watch": ["athletics", "insight"],
    "far traveler": ["insight", "perception"],
}

BACKGROUND_ALIASES = {
    "streetperformer": "entertainer",
    "entertainerstreetperformer": "entertainer",
    "guildartisan": "guild artisan",
    "folkhero": "folk hero",
    "citywatch": "city watch",
    "fartraveler": "far traveler",
}

SIMPLE_WEAPONS = {
    "club",
    "dagger",
    "greatclub",
    "handaxe",
    "javelin",
    "light hammer",
    "mace",
    "quarterstaff",
    "sickle",
    "spear",
    "light crossbow",
    "dart",
    "shortbow",
    "sling",
}

MARTIAL_WEAPONS = {
    "battleaxe",
    "flail",
    "glaive",
    "greataxe",
    "greatsword",
    "halberd",
    "lance",
    "longsword",
    "maul",
    "morningstar",
    "pike",
    "rapier",
    "scimitar",
    "shortsword",
    "trident",
    "war pick",
    "warhammer",
    "whip",
    "blowgun",
    "hand crossbow",
    "heavy crossbow",
    "longbow",
    "net",
}

ARMOR_GROUPS = {
    "light armor",
    "medium armor",
    "heavy armor",
    "shields",
}

CLASS_RULES = {
    "barbarian": {
        "hit_die": 12,
        "saving_throws": {"STR", "CON"},
        "skill_count": 2,
        "skill_options": {"animal", "athletics", "intimidation", "nature", "perception", "survival"},
        "armor_proficiencies": {"light armor", "medium armor", "shields"},
        "weapon_proficiencies": {"simple weapons", "martial weapons"},
        "spellcasting": None,
    },
    "bard": {
        "hit_die": 8,
        "saving_throws": {"DEX", "CHA"},
        "skill_count": 3,
        "skill_options": set(SKILL_TO_ABILITY.keys()),
        "armor_proficiencies": {"light armor"},
        "weapon_proficiencies": {"simple weapons", "hand crossbow", "longsword", "rapier", "shortsword"},
        "spellcasting": {"type": "known", "ability": "CHA"},
    },
    "cleric": {
        "hit_die": 8,
        "saving_throws": {"WIS", "CHA"},
        "skill_count": 2,
        "skill_options": {"history", "insight", "medicine", "persuasion", "religion"},
        "armor_proficiencies": {"light armor", "medium armor", "shields"},
        "weapon_proficiencies": {"simple weapons"},
        "spellcasting": {"type": "prepared", "ability": "WIS"},
    },
    "druid": {
        "hit_die": 8,
        "saving_throws": {"INT", "WIS"},
        "skill_count": 2,
        "skill_options": {"arcana", "animal", "insight", "medicine", "nature", "perception", "religion", "survival"},
        "armor_proficiencies": {"light armor", "medium armor", "shields"},
        "weapon_proficiencies": {"club", "dagger", "dart", "javelin", "mace", "quarterstaff", "scimitar", "sickle", "sling", "spear"},
        "spellcasting": {"type": "prepared", "ability": "WIS"},
    },
    "fighter": {
        "hit_die": 10,
        "saving_throws": {"STR", "CON"},
        "skill_count": 2,
        "skill_options": {"acrobatics", "animal", "athletics", "history", "insight", "intimidation", "perception", "survival"},
        "armor_proficiencies": {"light armor", "medium armor", "heavy armor", "shields"},
        "weapon_proficiencies": {"simple weapons", "martial weapons"},
        "spellcasting": None,
    },
    "monk": {
        "hit_die": 8,
        "saving_throws": {"STR", "DEX"},
        "skill_count": 2,
        "skill_options": {"acrobatics", "athletics", "history", "insight", "religion", "stealth"},
        "armor_proficiencies": set(),
        "weapon_proficiencies": {"simple weapons", "shortsword"},
        "spellcasting": None,
    },
    "paladin": {
        "hit_die": 10,
        "saving_throws": {"WIS", "CHA"},
        "skill_count": 2,
        "skill_options": {"athletics", "insight", "intimidation", "medicine", "persuasion", "religion"},
        "armor_proficiencies": {"light armor", "medium armor", "heavy armor", "shields"},
        "weapon_proficiencies": {"simple weapons", "martial weapons"},
        "spellcasting": {"type": "prepared_half", "ability": "CHA"},
    },
    "ranger": {
        "hit_die": 10,
        "saving_throws": {"STR", "DEX"},
        "skill_count": 3,
        "skill_options": {"animal", "athletics", "insight", "investigation", "nature", "perception", "stealth", "survival"},
        "armor_proficiencies": {"light armor", "medium armor", "shields"},
        "weapon_proficiencies": {"simple weapons", "martial weapons"},
        "spellcasting": {"type": "known_half", "ability": "WIS"},
    },
    "rogue": {
        "hit_die": 8,
        "saving_throws": {"DEX", "INT"},
        "skill_count": 4,
        "skill_options": {"acrobatics", "athletics", "deception", "insight", "intimidation", "investigation", "perception", "performance", "persuasion", "sleightofhand", "stealth"},
        "armor_proficiencies": {"light armor"},
        "weapon_proficiencies": {"simple weapons", "hand crossbow", "longsword", "rapier", "shortsword"},
        "spellcasting": None,
    },
    "sorcerer": {
        "hit_die": 6,
        "saving_throws": {"CON", "CHA"},
        "skill_count": 2,
        "skill_options": {"arcana", "deception", "insight", "intimidation", "persuasion", "religion"},
        "armor_proficiencies": set(),
        "weapon_proficiencies": {"dagger", "dart", "sling", "quarterstaff", "light crossbow"},
        "spellcasting": {"type": "known", "ability": "CHA"},
    },
    "warlock": {
        "hit_die": 8,
        "saving_throws": {"WIS", "CHA"},
        "skill_count": 2,
        "skill_options": {"arcana", "deception", "history", "intimidation", "investigation", "nature", "religion"},
        "armor_proficiencies": {"light armor"},
        "weapon_proficiencies": {"simple weapons"},
        "spellcasting": {"type": "known_warlock", "ability": "CHA"},
    },
    "wizard": {
        "hit_die": 6,
        "saving_throws": {"INT", "WIS"},
        "skill_count": 2,
        "skill_options": {"arcana", "history", "insight", "investigation", "medicine", "religion"},
        "armor_proficiencies": set(),
        "weapon_proficiencies": {"dagger", "dart", "sling", "quarterstaff", "light crossbow"},
        "spellcasting": {"type": "prepared", "ability": "INT"},
    },
    "artificer": {
        "hit_die": 8,
        "saving_throws": {"CON", "INT"},
        "skill_count": 2,
        "skill_options": {"arcana", "history", "investigation", "medicine", "nature", "perception", "sleightofhand"},
        "armor_proficiencies": {"light armor", "medium armor", "shields"},
        "weapon_proficiencies": {"simple weapons"},
        "spellcasting": {"type": "prepared_artificer", "ability": "INT"},
    },
}

RACE_EXTRA_WEAPON_PROFS = {
    "dwarf": {"battleaxe", "handaxe", "light hammer", "warhammer"},
    "high elf": {"longsword", "shortsword", "shortbow", "longbow"},
    "wood elf": {"longsword", "shortsword", "shortbow", "longbow"},
}

RACE_DEFAULT_FEATURES = {
    "half-elf": ["Darkvision", "Fey Ancestry"],
}

RACE_DEFAULT_SENSES = {
    "half-elf": "darkvision 60 ft.",
}

NAME_PARTS = {
    "human": {
        "first": ["Alden", "Mira", "Kaelan", "Seren", "Tavian", "Lyra", "Rowan", "Cassian", "Elira", "Darian", "Iris", "Nadia"],
        "last": ["Morrow", "Vale", "Ashdown", "Hawke", "Fenmere", "Blackwater", "Marlowe", "Stone", "Reeve", "Thorne", "Voss", "Weatherby"],
    },
    "elf": {
        "first": ["Aelar", "Sylvaris", "Lethira", "Faelar", "Ilyrana", "Vaeril", "Thamior", "Naivara", "Eryndor", "Shalana", "Myriil", "Caelynn"],
        "last": ["Amakiir", "Galanodel", "Holimion", "Liadon", "Xiloscient", "Ilphelkiir", "Nailo", "Siannodel", "Meliamne", "Yrthraethra"],
    },
    "half-elf": {
        "first": ["Kaelis", "Liora", "Theren", "Anwyn", "Rylan", "Selenne", "Corin", "Elaria", "Marek", "Nyra", "Tallis", "Virel"],
        "last": ["Moonbrook", "Evenwood", "Dawnmere", "Ashvale", "Riversong", "Glenhaven", "Stormwillow", "Thornmere", "Silverfen", "Valecrest"],
    },
    "dwarf": {
        "first": ["Bruen", "Dagna", "Torin", "Helja", "Orsik", "Vistra", "Rurik", "Sannl", "Baern", "Kathra"],
        "last": ["Ironfist", "Graniteheart", "Battlehammer", "Stonevein", "Deepdelver", "Forgeborn", "Anvilhand", "Goldfinder"],
    },
    "halfling": {
        "first": ["Perrin", "Marigold", "Roscoe", "Tessa", "Bramble", "Cora", "Milo", "Lavinia", "Nedda", "Tobin"],
        "last": ["Brushgather", "Underbough", "Tealeaf", "Goodbarrel", "Highhill", "Hilltopple", "Greenbottle", "Softstep"],
    },
    "gnome": {
        "first": ["Nib", "Bimpnottin", "Ellyjoy", "Fonkin", "Loopmottin", "Tana", "Wrenn", "Fizzwick", "Boddynock", "Zanna"],
        "last": ["Nackle", "Murnig", "Turen", "Ningel", "Daergel", "Scheppen", "Timbers", "Folkor"],
    },
    "dragonborn": {
        "first": ["Arjhan", "Balasar", "Donaar", "Kriv", "Medrash", "Nadarr", "Rhogar", "Torinn", "Akra", "Kava"],
        "last": ["Clethtinthiallor", "Daardendrian", "Delmirev", "Kepeshkmolik", "Myastan", "Turnuroth", "Verthisathurgiesh"],
    },
    "tiefling": {
        "first": ["Akmenos", "Orianna", "Leucis", "Nyx", "Morthos", "Seraphine", "Kallista", "Zevran", "Riven", "Asha"],
        "last": ["Nightbrand", "Vexley", "Embermoor", "Duskwell", "Hellscar", "Ashthorn", "Blackflame", "Mireveil"],
    },
    "half-orc": {
        "first": ["Grom", "Shara", "Dorn", "Urga", "Mugra", "Ront", "Baggi", "Thokk", "Ovak", "Keth"],
        "last": ["Skullcleaver", "Stonejaw", "Redfang", "Ironhide", "Goreborn", "Blacktusk", "Ashscar", "Bonebreaker"],
    },
    "orc": {
        "first": ["Hruk", "Yagra", "Morg", "Shump", "Zog", "Thura", "Brakka", "Drenk"],
        "last": ["Skullsplitter", "Bloodtusk", "Grimmaw", "Ironscar", "Rotfang", "Warcaller"],
    },
    "goblin": {
        "first": ["Skrik", "Nix", "Boggle", "Razzik", "Tikka", "Grib", "Sniv", "Mogget"],
        "last": ["Ratchet", "Sootnose", "Quickshiv", "Mudsnare", "Cracktooth", "Bogsnip"],
    },
    "default": {
        "first": ["Kael", "Lira", "Toren", "Nyra", "Ari", "Sel", "Corin", "Maeve", "Darian", "Veya"],
        "last": ["Ashfall", "Mournwood", "Vale", "Thorn", "Duskryn", "Wintermere", "Blackbriar", "Starseer"],
    },
}

SUBCLASS_SPELLCASTING = {
    ("rogue", "arcane trickster"): {
        "type": "third_known",
        "ability": "INT",
        "forced_cantrips": ["Mage Hand"],
        "source_class": "wizard",
    },
    ("fighter", "eldritch knight"): {
        "type": "third_known",
        "ability": "INT",
        "forced_cantrips": [],
        "source_class": "wizard",
    },
}

SUBCLASS_DEFAULT_SPELLS = {
    ("rogue", "arcane trickster"): {
        "cantrip": ["Mage Hand", "Minor Illusion", "Prestidigitation"],
        "1": ["Charm Person", "Disguise Self", "Silent Image", "Shield"],
    },
    ("fighter", "eldritch knight"): {
        "cantrip": ["Fire Bolt", "Mage Hand"],
        "1": ["Shield", "Magic Missile", "Protection from Evil and Good"],
    },
}

CLASS_DEFAULT_SPELLS = {
    "bard": {
        "cantrip": ["Vicious Mockery", "Prestidigitation", "Mage Hand", "Minor Illusion"],
        "1": ["Charm Person", "Healing Word", "Dissonant Whispers", "Faerie Fire", "Detect Magic"],
        "2": ["Invisibility", "Suggestion"],
    },
    "cleric": {
        "cantrip": ["Guidance", "Sacred Flame", "Spare the Dying", "Thaumaturgy", "Mending"],
        "1": ["Bless", "Cure Wounds", "Healing Word", "Sanctuary", "Shield of Faith", "Command"],
        "2": ["Aid", "Lesser Restoration", "Prayer of Healing", "Spiritual Weapon"],
        "3": ["Revivify", "Dispel Magic", "Spirit Guardians"],
        "4": ["Death Ward", "Freedom of Movement"],
        "5": ["Greater Restoration", "Mass Cure Wounds"],
        "6": ["Heal", "Blade Barrier"],
    },
    "druid": {
        "cantrip": ["Guidance", "Produce Flame", "Thorn Whip"],
        "1": ["Cure Wounds", "Faerie Fire", "Fog Cloud", "Healing Word", "Detect Magic"],
    },
    "paladin": {
        "1": ["Bless", "Cure Wounds", "Detect Magic", "Command", "Shield of Faith"],
        "2": ["Lesser Restoration", "Magic Weapon", "Aid"],
        "3": ["Revivify", "Aura of Vitality"],
        "4": ["Death Ward", "Banishment"],
    },
    "ranger": {
        "1": ["Cure Wounds", "Detect Magic", "Fog Cloud", "Hunter's Mark"],
        "2": ["Pass Without Trace", "Spike Growth", "Lesser Restoration"],
        "3": ["Conjure Animals", "Lightning Arrow"],
    },
    "sorcerer": {
        "cantrip": ["Fire Bolt", "Mage Hand", "Prestidigitation", "Ray of Frost"],
        "1": ["Magic Missile", "Shield", "Burning Hands", "Charm Person"],
        "2": ["Misty Step", "Invisibility"],
        "3": ["Fly", "Counterspell"],
    },
    "warlock": {
        "cantrip": ["Eldritch Blast", "Mage Hand", "Minor Illusion", "Prestidigitation"],
        "1": ["Charm Person", "Hex"],
        "2": ["Misty Step", "Invisibility"],
        "3": ["Fly"],
    },
    "wizard": {
        "cantrip": ["Fire Bolt", "Mage Hand", "Prestidigitation", "Ray of Frost", "Mending"],
        "1": ["Magic Missile", "Shield", "Detect Magic", "Find Familiar", "Sleep"],
        "2": ["Invisibility", "Misty Step", "Mirror Image", "Scorching Ray"],
        "3": ["Fly", "Counterspell", "Fireball"],
        "4": ["Dimension Door", "Polymorph"],
        "5": ["Hold Monster", "Cone of Cold"],
    },
    "artificer": {
        "cantrip": ["Mending", "Mage Hand", "Fire Bolt"],
        "1": ["Cure Wounds", "Faerie Fire", "Grease", "Identify"],
    },
}

SUBCLASS_REQUIRED_FEATURES = {
    ("rogue", "arcane trickster"): ["Arcane Trickster Spellcasting", "Mage Hand Legerdemain"],
}

SUBCLASS_FORBIDDEN_FEATURES = {
    ("rogue", "arcane trickster"): {
        "Sculpt Spells",
        "Arcane Recovery",
    },
}

FULL_CASTER_MAX_LEVEL = [0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 9, 9]
HALF_CASTER_MAX_LEVEL = [0, 0, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5]
WARLOCK_MAX_LEVEL = [0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5]

CANTRIPS_KNOWN = {
    "bard":       [0, 2, 2, 2, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
    "cleric":     [0, 3, 3, 3, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5],
    "druid":      [0, 2, 2, 2, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
    "sorcerer":   [0, 4, 4, 4, 5, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6],
    "warlock":    [0, 2, 2, 2, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
    "wizard":     [0, 3, 3, 3, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5],
    "artificer":  [0, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4],
}

SPELLS_KNOWN = {
    "bard":      [0, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 15, 16, 18, 19, 19, 20, 22, 22, 22],
    "sorcerer":  [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 12, 13, 13, 14, 14, 15, 15, 15, 15],
    "warlock":   [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 11, 11, 12, 12, 13, 13, 14, 14, 15, 15],
    "ranger":    [0, 0, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11],
}

# Curated reverse class mapping for common SRD/PHB spells. This catches major cross-class errors.
SPELL_CLASS_ALLOWLIST = {
    "acid splash": {"artificer", "sorcerer", "wizard"},
    "astral projection": {"cleric", "warlock", "wizard"},
    "bless": {"cleric", "paladin"},
    "burning hands": {"sorcerer", "wizard"},
    "charm person": {"bard", "druid", "sorcerer", "warlock", "wizard"},
    "cloudkill": {"sorcerer", "wizard"},
    "color spray": {"bard", "sorcerer", "wizard"},
    "command": {"cleric", "paladin"},
    "comprehend languages": {"bard", "sorcerer", "warlock", "wizard"},
    "counterspell": {"sorcerer", "warlock", "wizard"},
    "cure wounds": {"artificer", "bard", "cleric", "druid", "paladin", "ranger"},
    "detect magic": {"bard", "cleric", "druid", "paladin", "ranger", "sorcerer", "wizard"},
    "dissonant whispers": {"bard"},
    "disguise self": {"artificer", "bard", "sorcerer", "wizard"},
    "dimension door": {"bard", "sorcerer", "warlock", "wizard"},
    "disintegrate": {"sorcerer", "wizard"},
    "eldritch blast": {"warlock"},
    "feather fall": {"bard", "sorcerer", "wizard"},
    "faerie fire": {"artificer", "bard", "druid"},
    "find familiar": {"wizard"},
    "fire bolt": {"artificer", "sorcerer", "wizard"},
    "fireball": {"sorcerer", "wizard"},
    "fire wall": {"druid", "sorcerer", "wizard"},
    "fog cloud": {"druid", "ranger", "sorcerer", "wizard"},
    "fly": {"sorcerer", "warlock", "wizard"},
    "grease": {"wizard", "artificer"},
    "guidance": {"artificer", "cleric", "druid"},
    "hex": {"warlock"},
    "aid": {"artificer", "cleric", "paladin"},
    "healing word": {"bard", "cleric", "druid"},
    "hold monster": {"bard", "cleric", "sorcerer", "warlock", "wizard"},
    "identify": {"artificer", "bard", "wizard"},
    "invisibility": {"bard", "sorcerer", "warlock", "wizard"},
    "lesser restoration": {"artificer", "bard", "cleric", "druid", "paladin", "ranger"},
    "mage armor": {"sorcerer", "wizard"},
    "mage hand": {"artificer", "bard", "sorcerer", "warlock", "wizard"},
    "magic missile": {"sorcerer", "wizard"},
    "mending": {"artificer", "bard", "cleric", "druid", "sorcerer", "wizard"},
    "message": {"artificer", "bard", "sorcerer", "wizard"},
    "misty step": {"sorcerer", "warlock", "wizard"},
    "minor illusion": {"bard", "sorcerer", "warlock", "wizard"},
    "power word heal": {"bard", "cleric"},
    "power word kill": {"bard", "sorcerer", "warlock", "wizard"},
    "prestidigitation": {"artificer", "bard", "sorcerer", "warlock", "wizard"},
    "prayer of healing": {"cleric"},
    "protection from evil and good": {"cleric", "paladin", "warlock", "wizard"},
    "produce flame": {"druid"},
    "ray of frost": {"artificer", "sorcerer", "wizard"},
    "revivify": {"artificer", "cleric", "paladin", "ranger"},
    "sacred flame": {"cleric"},
    "sanctuary": {"cleric"},
    "scorching ray": {"sorcerer", "wizard"},
    "shield": {"sorcerer", "wizard"},
    "shield of faith": {"cleric", "paladin"},
    "shocking grasp": {"artificer", "sorcerer", "wizard"},
    "silent image": {"bard", "sorcerer", "wizard"},
    "sleep": {"bard", "sorcerer", "wizard"},
    "spare the dying": {"artificer", "cleric"},
    "spiritual weapon": {"cleric"},
    "suggestion": {"bard", "sorcerer", "warlock", "wizard"},
    "tashas hideous laughter": {"bard", "wizard"},
    "teleport": {"bard", "sorcerer", "wizard"},
    "thaumaturgy": {"cleric"},
    "thorn whip": {"artificer", "druid"},
    "thunderwave": {"bard", "druid", "sorcerer", "wizard"},
    "vicious mockery": {"bard"},
}

SPELL_LEVEL_OVERRIDES = {
    "acid splash": 0,
    "astral projection": 9,
    "bless": 1,
    "burning hands": 1,
    "charm person": 1,
    "cloudkill": 5,
    "color spray": 1,
    "command": 1,
    "comprehend languages": 1,
    "counterspell": 3,
    "cure wounds": 1,
    "detect magic": 1,
    "dissonant whispers": 1,
    "disguise self": 1,
    "dimension door": 4,
    "disintegrate": 6,
    "eldritch blast": 0,
    "feather fall": 1,
    "faerie fire": 1,
    "find familiar": 1,
    "fire bolt": 0,
    "fireball": 3,
    "fire wall": 4,
    "fog cloud": 1,
    "fly": 3,
    "grease": 1,
    "guidance": 0,
    "aid": 2,
    "hex": 1,
    "healing word": 1,
    "hold monster": 5,
    "identify": 1,
    "invisibility": 2,
    "lesser restoration": 2,
    "mage armor": 1,
    "mage hand": 0,
    "magic missile": 1,
    "mending": 0,
    "message": 0,
    "misty step": 2,
    "minor illusion": 0,
    "power word heal": 9,
    "power word kill": 9,
    "prestidigitation": 0,
    "prayer of healing": 2,
    "protection from evil and good": 1,
    "produce flame": 0,
    "ray of frost": 0,
    "revivify": 3,
    "sacred flame": 0,
    "sanctuary": 1,
    "scorching ray": 2,
    "shield": 1,
    "shield of faith": 1,
    "shocking grasp": 0,
    "silent image": 1,
    "sleep": 1,
    "spare the dying": 0,
    "spiritual weapon": 2,
    "suggestion": 2,
    "tashas hideous laughter": 1,
    "teleport": 7,
    "thaumaturgy": 0,
    "thorn whip": 0,
    "thunderwave": 1,
    "vicious mockery": 0,
}


def normalize_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def canonical_background_key(text: str) -> str:
    key = normalize_key(text)
    if key in BACKGROUND_ALIASES:
        return BACKGROUND_ALIASES[key]
    for bg in BACKGROUND_SKILLS:
        if normalize_key(bg) == key or normalize_key(bg) in key or key in normalize_key(bg):
            return bg
    return ""


def canonical_class_key(text: str) -> str:
    key = normalize_key((text or "").split("/")[0].split("(")[0].strip())
    for cls in CLASS_RULES:
        if normalize_key(cls) == key:
            return cls
    return ""


def canonical_race_key(text: str) -> str:
    value = (text or "").strip().lower()
    for race in RACE_EXTRA_WEAPON_PROFS:
        if race == value:
            return race
    if "dwarf" in value:
        return "dwarf"
    return value


def default_racial_features(race_key: str) -> list[str]:
    return list(RACE_DEFAULT_FEATURES.get(race_key, []))


def default_racial_senses(race_key: str) -> str:
    return RACE_DEFAULT_SENSES.get(race_key, "")


def generate_diverse_name(race_key: str) -> str:
    key = race_key or "default"
    if key not in NAME_PARTS:
        if "elf" in key:
            key = "elf" if "half" not in key else "half-elf"
        elif "dwarf" in key:
            key = "dwarf"
        elif "gnome" in key:
            key = "gnome"
        elif "halfling" in key:
            key = "halfling"
        elif "dragonborn" in key:
            key = "dragonborn"
        elif "tiefling" in key:
            key = "tiefling"
        elif "orc" in key:
            key = "half-orc" if "half" in key else "orc"
        elif "goblin" in key:
            key = "goblin"
        elif "human" in key:
            key = "human"
        else:
            key = "default"
    parts = NAME_PARTS[key]
    return f"{random.choice(parts['first'])} {random.choice(parts['last'])}"


def spellcasting_profile(class_key: str, subclass: str = "") -> dict | None:
    subclass_key = normalize_key(subclass or "")
    for (candidate_class, candidate_subclass), override in SUBCLASS_SPELLCASTING.items():
        if candidate_class == class_key and normalize_key(candidate_subclass) == subclass_key:
            return override
    return (CLASS_RULES.get(class_key) or {}).get("spellcasting")


def build_has_spell_source(class_key: str, subclass: str, race_key: str, features: list[str]) -> bool:
    if spellcasting_profile(class_key, subclass):
        return True

    feature_text = " ".join(str(feature or "") for feature in (features or [])).lower()
    explicit_magic_markers = (
        "drow magic",
        "cantrip",
        "spellcasting",
        "innate spellcasting",
    )
    if any(marker in feature_text for marker in explicit_magic_markers):
        return True

    # Conservative racial handling: only force spells when the chosen racial features
    # explicitly indicate magical traits. Ordinary races without such features may remain empty.
    if race_key in {"drow", "high elf"} and feature_text:
        if "magic" in feature_text or "cantrip" in feature_text:
            return True

    return False


def normalize_features_for_build(features: list[str], class_key: str, subclass: str) -> tuple[list[str], list[str]]:
    normalized = []
    seen = set()
    for feature in features or []:
        text = str(feature).strip()
        if not text:
            continue
        key = text.lower()
        if key not in seen:
            seen.add(key)
            normalized.append(text)

    corrected = []
    subclass_key = normalize_key(subclass or "")
    forbidden_set = set()
    for (candidate_class, candidate_subclass), names in SUBCLASS_FORBIDDEN_FEATURES.items():
        if candidate_class == class_key and normalize_key(candidate_subclass) == subclass_key:
            forbidden_set = names
            break
    forbidden = {name.lower() for name in forbidden_set}
    if forbidden:
        kept = []
        for feature in normalized:
            if feature.lower() in forbidden:
                corrected.append(f"removed invalid subclass feature: {feature}")
            else:
                kept.append(feature)
        normalized = kept

    existing = {feature.lower() for feature in normalized}
    required_features = []
    for (candidate_class, candidate_subclass), names in SUBCLASS_REQUIRED_FEATURES.items():
        if candidate_class == class_key and normalize_key(candidate_subclass) == subclass_key:
            required_features = names
            break
    for required in required_features:
        if required.lower() not in existing:
            normalized.append(required)
            existing.add(required.lower())
            corrected.append(f"added required subclass feature: {required}")

    return normalized, corrected


def default_spells_for_build(class_key: str, subclass: str) -> dict[str, list[str]]:
    subclass_key = normalize_key(subclass or "")
    defaults = None
    for (candidate_class, candidate_subclass), spell_map in SUBCLASS_DEFAULT_SPELLS.items():
        if candidate_class == class_key and normalize_key(candidate_subclass) == subclass_key:
            defaults = spell_map
            break
    if defaults is None:
        defaults = CLASS_DEFAULT_SPELLS.get(class_key, {})
    return {bucket: list(names) for bucket, names in defaults.items()}


def generated_fallback_spells_for_build(class_key: str, subclass: str, level: int, spellcasting_ability_mod: int) -> dict[str, list[str]]:
    capacity = spell_capacity_for_build(class_key, subclass, level, spellcasting_ability_mod)
    if capacity["rule"] == "noncaster":
        return {}

    profile = spellcasting_profile(class_key, subclass) or {}
    effective_spell_class = profile.get("source_class", class_key)
    corpus = spell_corpus()
    priority = default_spells_for_build(class_key, subclass)

    by_level: dict[int, list[str]] = {}
    for norm, allowed_classes in SPELL_CLASS_ALLOWLIST.items():
        if effective_spell_class not in allowed_classes:
            continue
        level_value = SPELL_LEVEL_OVERRIDES.get(norm)
        meta = corpus.get(norm)
        if level_value is None:
            if not meta:
                continue
            level_value = meta["level"]
        if level_value > capacity["max_spell_level"]:
            continue
        display_name = meta["name"] if meta else norm.title()
        by_level.setdefault(level_value, [])
        if display_name not in by_level[level_value]:
            by_level[level_value].append(display_name)

    result: dict[str, list[str]] = {}

    cantrip_pool = list(priority.get("cantrip", []))
    for required in profile.get("forced_cantrips", []):
        if required not in cantrip_pool:
            cantrip_pool.insert(0, required)
    for name in sorted(by_level.get(0, [])):
        if name not in cantrip_pool:
            cantrip_pool.append(name)
    if capacity["cantrips"] > 0 and cantrip_pool:
        result["cantrip"] = cantrip_pool[: capacity["cantrips"]]

    if capacity["non_cantrip_limit"] <= 0:
        return result

    leveled_selected: dict[str, list[str]] = {}
    total = 0
    max_level = max(1, capacity["max_spell_level"])

    per_level_pools: dict[int, list[str]] = {}
    for lvl in range(1, max_level + 1):
        pool = list(priority.get(str(lvl), []))
        for name in sorted(by_level.get(lvl, [])):
            if name not in pool:
                pool.append(name)
        per_level_pools[lvl] = pool

    while total < capacity["non_cantrip_limit"]:
        added_this_round = False
        for lvl in range(1, max_level + 1):
            bucket = str(lvl)
            selected = leveled_selected.setdefault(bucket, [])
            pool = per_level_pools.get(lvl, [])
            next_choice = next((name for name in pool if name not in selected), None)
            if next_choice:
                selected.append(next_choice)
                total += 1
                added_this_round = True
                if total >= capacity["non_cantrip_limit"]:
                    break
        if not added_this_round:
            break

    for bucket, names in leveled_selected.items():
        if names:
            result[bucket] = names

    return result


def normalize_skill_name(name: str) -> str:
    key = re.sub(r"[^a-z]", "", (name or "").lower())
    aliases = {"animalhandling": "animal", "sleightofhand": "sleightofhand"}
    return aliases.get(key, key)


def dedupe(items):
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def prof_bonus(level: int) -> int:
    return 2 + (max(1, int(level)) - 1) // 4


def ability_mod(score: int) -> int:
    return (int(score) - 10) // 2


def titleize_weapon(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split())


def normalize_background_skills(background: str):
    bg_key = canonical_background_key(background)
    return bg_key, list(BACKGROUND_SKILLS.get(bg_key, []))


def normalize_skill_proficiencies(skill_profs, class_key: str, background: str):
    bg_key, bg_skills = normalize_background_skills(background)
    provided = [normalize_skill_name(p) for p in (skill_profs or [])]
    provided = [p for p in provided if p in SKILL_TO_ABILITY]
    rules = CLASS_RULES.get(class_key) or {}
    options = set(rules.get("skill_options") or SKILL_TO_ABILITY.keys())
    count = rules.get("skill_count")
    allowed = options | set(bg_skills)
    invalid = [p for p in provided if p not in allowed]
    normalized = dedupe([p for p in provided if p in allowed] + [s for s in bg_skills if s in allowed])
    if count is not None:
        max_total = count + len(bg_skills)
        normalized = normalized[:max_total]
        while len(normalized) < max_total:
            remaining = [s for s in options if s not in normalized]
            if not remaining:
                break
            normalized.append(sorted(remaining)[0])
    return normalized, invalid, bg_key


def normalize_saving_throw_proficiencies(saving_throw_profs, class_key: str):
    expected = set((CLASS_RULES.get(class_key) or {}).get("saving_throws") or [])
    provided = {str(p).upper() for p in (saving_throw_profs or []) if str(p).upper() in ABILITIES}
    invalid = sorted(provided - expected)
    if expected:
        return sorted(expected), invalid
    return sorted(provided), invalid


def normalize_armor_proficiencies(armor_profs, class_key: str):
    allowed = set((CLASS_RULES.get(class_key) or {}).get("armor_proficiencies") or [])
    normalized = []
    invalid = []
    for prof in armor_profs or []:
        key = (prof or "").strip().lower()
        if key in allowed:
            normalized.append(key)
        else:
            invalid.append(prof)
    if allowed:
        normalized = sorted(allowed)
    return normalized, invalid


def _weapon_allowed(name: str, allowed_groups: set[str], race_key: str):
    if name in allowed_groups:
        return True
    if "simple weapons" in allowed_groups and name in SIMPLE_WEAPONS:
        return True
    if "martial weapons" in allowed_groups and name in MARTIAL_WEAPONS:
        return True
    if name in (RACE_EXTRA_WEAPON_PROFS.get(race_key) or set()):
        return True
    return False


def normalize_weapon_proficiencies(weapon_profs, class_key: str, race_key: str):
    allowed_groups = set((CLASS_RULES.get(class_key) or {}).get("weapon_proficiencies") or [])
    allowed_groups |= set(RACE_EXTRA_WEAPON_PROFS.get(race_key) or set())
    invalid = []
    for prof in weapon_profs or []:
        key = (prof or "").strip().lower()
        if not _weapon_allowed(key, allowed_groups, race_key):
            invalid.append(prof)
    normalized = sorted(allowed_groups)
    return normalized, invalid


def compute_hit_points(class_key: str, level: int, con_score: int, parsed_hp=None):
    rules = CLASS_RULES.get(class_key) or {}
    hit_die = rules.get("hit_die")
    if not hit_die or level <= 0:
        return parsed_hp, {"source": "model", "reason": "no class hit die available"}

    con_mod = ability_mod(con_score)
    first_level = hit_die + con_mod
    later_levels = max(0, level - 1)
    average_per_level = (hit_die // 2) + 1 + con_mod
    total = first_level + later_levels * average_per_level
    return total, {
        "source": "deterministic",
        "class": class_key,
        "hit_die": f"d{hit_die}",
        "level": level,
        "constitution_modifier": con_mod,
        "first_level_hp": first_level,
        "levels_after_first": later_levels,
        "average_hp_per_level_after_first": average_per_level,
        "total": total,
        "model_hp": parsed_hp,
    }


def compute_armor_class(class_key: str, subclass: str, stats: dict, equipment: list[str], parsed_ac=None):
    dex_mod = ability_mod(stats["DEX"])
    con_mod = ability_mod(stats["CON"])
    wis_mod = ability_mod(stats["WIS"])
    equipment_l = [e.lower() for e in (equipment or [])]

    armor_choice = None
    base = 10
    dex_component = dex_mod
    notes = []

    armor_table = [
        ("plate", 18, 0),
        ("splint", 17, 0),
        ("chain mail", 16, 0),
        ("ring mail", 14, 0),
        ("half plate", 15, 2),
        ("breastplate", 14, 2),
        ("scale", 14, 2),
        ("chain shirt", 13, 2),
        ("hide", 12, 2),
        ("studded leather", 12, None),
        ("padded", 11, None),
        ("leather", 11, None),
    ]

    for armor_name, armor_base, dex_cap in armor_table:
        if any(armor_name in item for item in equipment_l):
            armor_choice = armor_name
            base = armor_base
            dex_component = min(dex_mod, dex_cap) if dex_cap is not None else dex_mod
            break

    if armor_choice is None:
        if class_key == "monk":
            base = 10
            dex_component = dex_mod
            notes.append("monk unarmored defense")
            total = base + dex_component + wis_mod
        elif class_key == "barbarian":
            base = 10
            dex_component = dex_mod
            notes.append("barbarian unarmored defense")
            total = base + dex_component + con_mod
        elif class_key == "sorcerer" and "draconic" in (subclass or "").lower():
            base = 13
            dex_component = dex_mod
            notes.append("draconic resilience")
            total = base + dex_component
        else:
            total = base + dex_component
    else:
        total = base + dex_component
        notes.append(f"armor: {armor_choice}")

    shield_bonus = 2 if any("shield" in item for item in equipment_l) else 0
    total += shield_bonus

    return total, {
        "source": "deterministic",
        "class": class_key,
        "subclass": subclass,
        "base_ac": base,
        "dex_modifier_applied": dex_component,
        "shield_bonus": shield_bonus,
        "armor": armor_choice or "unarmored",
        "notes": notes,
        "total": total,
        "model_ac": parsed_ac,
    }


@lru_cache(maxsize=1)
def spell_corpus():
    corpus = {}
    root = Path(__file__).resolve().parent / "data" / "split_md"
    if not root.exists():
        return corpus

    for path in root.rglob("*.md"):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[:6]
        except Exception:
            continue
        if not lines or not lines[0].startswith("# "):
            continue
        name = lines[0][2:].strip()
        norm = normalize_spell_name(name)
        if norm in {"spelllist", "spelllists", "spellcasting", "cantrips", "build", "level"}:
            continue
        level = None
        joined = " ".join(lines[1:4]).lower()
        if "cantrip" in joined:
            level = 0
        else:
            match = re.search(r"([1-9])(st|nd|rd|th)", joined)
            if match:
                level = int(match.group(1))
        if level is None:
            continue
        corpus[norm] = {"name": name, "level": level}
    return corpus


def normalize_spell_name(name: str) -> str:
    cleaned = (name or "").lower()
    cleaned = cleaned.replace("/", " ")
    cleaned = re.sub(r"[^a-z0-9 ]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def normalize_spell_dict(spells):
    normalized = {}
    for level_key, names in (spells or {}).items():
        key = str(level_key).strip().lower()
        bucket = "cantrip" if key in {"0", "cantrip", "cantrips"} else str(level_key).strip()
        if not isinstance(names, list):
            continue
        normalized[bucket] = [str(name).strip() for name in names if str(name).strip()]
    return normalized


def max_spell_level_for_class(class_key: str, level: int):
    if class_key not in CLASS_RULES:
        return 0
    spellcasting = (CLASS_RULES[class_key] or {}).get("spellcasting")
    if not spellcasting:
        return 0
    cast_type = spellcasting["type"]
    if cast_type in {"known", "prepared"}:
        return FULL_CASTER_MAX_LEVEL[level]
    if cast_type in {"known_half", "prepared_half", "prepared_artificer"}:
        return HALF_CASTER_MAX_LEVEL[level]
    if cast_type == "known_warlock":
        return WARLOCK_MAX_LEVEL[level]
    return 0


def spell_capacity_for_class(class_key: str, level: int, ability_mod_value: int):
    return spell_capacity_for_build(class_key, "", level, ability_mod_value)


def spell_capacity_for_build(class_key: str, subclass: str, level: int, ability_mod_value: int):
    spellcasting = spellcasting_profile(class_key, subclass)
    if not spellcasting or level <= 0:
        return {"cantrips": 0, "max_spell_level": 0, "non_cantrip_limit": 0, "rule": "noncaster"}

    cast_type = spellcasting["type"]
    cantrips = CANTRIPS_KNOWN.get(class_key, [0] * 21)[level] if class_key in CANTRIPS_KNOWN else 0
    max_spell_level = max_spell_level_for_class(class_key, level)

    if cast_type == "known":
        limit = SPELLS_KNOWN[class_key][level]
        rule = "known"
    elif cast_type == "known_half":
        limit = SPELLS_KNOWN[class_key][level]
        rule = "known_half"
    elif cast_type == "known_warlock":
        limit = SPELLS_KNOWN[class_key][level]
        rule = "known_warlock"
    elif cast_type == "prepared":
        limit = max(1, level + ability_mod_value)
        rule = "prepared"
    elif cast_type == "prepared_half":
        limit = max(1, (level // 2) + ability_mod_value) if level >= 2 else 0
        rule = "prepared_half"
    elif cast_type == "prepared_artificer":
        limit = max(1, (level // 2) + ability_mod_value)
        rule = "prepared_artificer"
    elif cast_type == "third_known":
        cantrips = 3 if level >= 3 else 0
        max_spell_level = 1 if level < 7 else 2 if level < 13 else 3 if level < 19 else 4
        if class_key == "rogue":
            limit = [0, 0, 0, 3, 4, 4, 4, 5, 6, 6, 7, 8, 8, 9, 10, 10, 11, 11, 11, 13, 13][level]
        elif class_key == "fighter":
            limit = [0, 0, 0, 3, 4, 4, 4, 5, 6, 6, 7, 8, 8, 9, 10, 10, 11, 11, 11, 13, 13][level]
        else:
            limit = 0
        rule = "third_known"
    else:
        limit = 0
        rule = cast_type

    return {
        "cantrips": cantrips,
        "max_spell_level": max_spell_level,
        "non_cantrip_limit": limit,
        "rule": rule,
    }


def minimum_expected_leveled_spells(capacity: dict) -> int:
    rule = capacity.get("rule")
    limit = int(capacity.get("non_cantrip_limit") or 0)
    max_spell_level = int(capacity.get("max_spell_level") or 0)
    if rule == "prepared":
        return min(limit, max(3, max_spell_level + 4))
    if rule == "prepared_half":
        return min(limit, max(2, max_spell_level + 3))
    if rule == "prepared_artificer":
        return min(limit, max(2, max_spell_level + 2))
    return limit


def validate_spells(spells, class_key: str, level: int, spellcasting_ability_mod: int, subclass: str = ""):
    normalized = normalize_spell_dict(spells)
    corpus = spell_corpus()
    issues = []
    total_non_cantrip = 0
    validated = {}
    capacity = spell_capacity_for_build(class_key, subclass, level, spellcasting_ability_mod)
    profile = spellcasting_profile(class_key, subclass) or {}
    effective_spell_class = profile.get("source_class", class_key)

    if capacity["rule"] == "noncaster" and normalized:
        return ["non-spellcasting class has spells"], {}, capacity

    for bucket, names in normalized.items():
        expected_level = 0 if bucket == "cantrip" else int(bucket) if str(bucket).isdigit() else None
        valid_names = []
        for name in names:
            norm = normalize_spell_name(name)
            meta = corpus.get(norm)
            if norm in SPELL_LEVEL_OVERRIDES:
                display_name = meta["name"] if meta else name.title()
                meta = {"name": display_name, "level": SPELL_LEVEL_OVERRIDES[norm]}
            if not meta:
                issues.append(f"unknown spell {name}")
                continue
            allowed_classes = SPELL_CLASS_ALLOWLIST.get(norm)
            if allowed_classes and effective_spell_class and effective_spell_class not in allowed_classes:
                issues.append(f"spell {meta['name']} not on {class_key} list")
                continue
            if expected_level is not None and meta["level"] != expected_level:
                issues.append(f"spell level mismatch for {meta['name']}")
                continue
            if meta["level"] > capacity["max_spell_level"]:
                issues.append(f"spell level too high for class level: {meta['name']}")
                continue
            valid_names.append(meta["name"])
        if valid_names:
            validated[bucket] = dedupe(valid_names)
            if bucket != "cantrip":
                total_non_cantrip += len(validated[bucket])

    cantrip_count = len(validated.get("cantrip", []))
    for required_cantrip in profile.get("forced_cantrips", []):
        if required_cantrip not in validated.get("cantrip", []):
            issues.append(f"missing required cantrip {required_cantrip}")
            validated.setdefault("cantrip", []).insert(0, required_cantrip)
    if "cantrip" in validated:
        validated["cantrip"] = dedupe(validated["cantrip"])
        cantrip_count = len(validated["cantrip"])

    if cantrip_count > capacity["cantrips"]:
        issues.append(f"too many cantrips ({cantrip_count}>{capacity['cantrips']})")
        validated["cantrip"] = validated.get("cantrip", [])[: capacity["cantrips"]]
        cantrip_count = len(validated.get("cantrip", []))
    elif capacity["cantrips"] > 0 and cantrip_count < capacity["cantrips"]:
        issues.append(f"too few cantrips ({cantrip_count}<{capacity['cantrips']})")

    required_leveled_spells = minimum_expected_leveled_spells(capacity)

    if total_non_cantrip > capacity["non_cantrip_limit"]:
        issues.append(f"too many leveled spells ({total_non_cantrip}>{capacity['non_cantrip_limit']})")
    elif capacity["rule"] in {"known", "known_half", "known_warlock", "third_known", "prepared", "prepared_half", "prepared_artificer"} and total_non_cantrip < required_leveled_spells:
        issues.append(f"too few leveled spells ({total_non_cantrip}<{required_leveled_spells})")

    return dedupe(issues), validated, capacity
