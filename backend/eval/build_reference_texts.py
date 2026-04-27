#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def build_reference_text(entity_type: str, prompt: dict) -> str:
    parts = [f"This reference describes a {entity_type} for D&D 5e."]
    if prompt.get("race"):
        parts.append(f"Race: {prompt['race']}.")
    if prompt.get("dnd_class"):
        parts.append(f"Class: {prompt['dnd_class']}.")
    if prompt.get("level") is not None:
        parts.append(f"Level: {prompt['level']}.")
    if prompt.get("alignment"):
        parts.append(f"Alignment: {prompt['alignment']}.")
    if prompt.get("concept"):
        parts.append(f"Concept: {prompt['concept']}")
    parts.append(
        "A strong answer should preserve the requested role, broad mechanical identity, and core thematic intent."
    )
    return " ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build simple reference texts from a benchmark prompt file.")
    parser.add_argument("prompts", help="Path to prompts JSON")
    parser.add_argument("--out", default="", help="Optional output JSON path")
    args = parser.parse_args()

    prompts_path = Path(args.prompts).resolve()
    data = json.load(prompts_path.open("r", encoding="utf-8"))

    references = {}
    for entity_type, items in data.items():
        for index, prompt in enumerate(items, start=1):
            prompt_id = f"{entity_type}_{index:02d}"
            references[prompt_id] = {
                "reference": build_reference_text(entity_type, prompt),
            }

    out_path = Path(args.out).resolve() if args.out else prompts_path.with_name(prompts_path.stem + "_references.json")
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(references, handle, indent=2)

    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
