#!/usr/bin/env python3
import argparse
import csv
import json
import os
from pathlib import Path
from statistics import mean
from typing import Any

from ragas import EvaluationDataset, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics.collections import (
    AnswerCorrectness,
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCES = ROOT / "eval" / "dissertation_references.json"
DEFAULT_PROMPTS = ROOT / "eval" / "dissertation_prompts.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def prompt_lookup(prompts: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    lookup = {}
    for entity_type, items in prompts.items():
        for index, item in enumerate(items, start=1):
            lookup[f"{entity_type}_{index:02d}"] = item
    return lookup


def build_user_input(entity_type: str, prompt: dict[str, Any]) -> str:
    parts = [f"Entity type: {entity_type}."]
    if prompt.get("race"):
        parts.append(f"Race: {prompt['race']}.")
    if prompt.get("dnd_class"):
        parts.append(f"Class: {prompt['dnd_class']}.")
    if prompt.get("level"):
        parts.append(f"Level: {prompt['level']}.")
    if prompt.get("alignment"):
        parts.append(f"Alignment: {prompt['alignment']}.")
    if prompt.get("concept"):
        parts.append(f"Concept: {prompt['concept']}")
    return " ".join(parts)


def render_parsed_output(parsed: dict[str, Any], entity_type: str) -> str:
    if not isinstance(parsed, dict):
        return ""

    basics = []
    for key in ["name", "race", "class", "subclass", "background", "alignment"]:
        value = parsed.get(key)
        if value:
            basics.append(f"{key}: {value}")
    if parsed.get("level") is not None:
        basics.append(f"level: {parsed.get('level')}")
    if parsed.get("hitPoints") is not None:
        basics.append(f"hp: {parsed.get('hitPoints')}")
    if parsed.get("armorClass") is not None:
        basics.append(f"ac: {parsed.get('armorClass')}")
    if parsed.get("speed") is not None:
        basics.append(f"speed: {parsed.get('speed')}")

    abilities = parsed.get("abilities") or {}
    ability_text = ", ".join(
        f"{key.upper()} {abilities.get(key, '—')}" for key in ["str", "dex", "con", "int", "wis", "cha"]
    )

    profs = ", ".join(parsed.get("skill_proficiencies") or [])
    saves = ", ".join(parsed.get("saving_throw_proficiencies") or [])
    armor = ", ".join(parsed.get("armor_proficiencies") or [])
    weapons = ", ".join(parsed.get("weapon_proficiencies") or [])

    spell_parts = []
    for level, names in (parsed.get("spells") or {}).items():
        label = "cantrips" if str(level).lower() in {"cantrip", "cantrips", "0"} else f"level {level}"
        spell_parts.append(f"{label}: {', '.join(names)}")
    spell_text = "; ".join(spell_parts)

    notes = parsed.get("notes") or parsed.get("short_blurb") or ""

    response_parts = [
        f"Generated {entity_type}.",
        "; ".join(basics),
        f"abilities: {ability_text}",
    ]
    if profs:
        response_parts.append(f"skills: {profs}")
    if saves:
        response_parts.append(f"saving throws: {saves}")
    if armor:
        response_parts.append(f"armor proficiencies: {armor}")
    if weapons:
        response_parts.append(f"weapon proficiencies: {weapons}")
    if spell_text:
        response_parts.append(f"spells: {spell_text}")
    if notes:
        response_parts.append(f"flavour: {notes}")
    return ". ".join(part for part in response_parts if part)


def build_dataset_rows(run_dir: Path, prompts_path: Path, references_path: Path) -> list[dict[str, Any]]:
    results_csv = run_dir / "results.csv"
    rows = load_csv(results_csv)
    prompt_map = prompt_lookup(load_json(prompts_path))
    references = load_json(references_path)

    samples = []
    for row in rows:
        artifact_path = run_dir / f"{row['id']}.json"
        artifact = load_json(artifact_path)
        payload = artifact.get("payload") or {}
        response = artifact.get("response") or {}
        parsed = response.get("parsed") or response.get("sheet_json") or {}
        prompt_id = row["prompt_id"]
        entity_type = row["entity_type"]
        prompt = prompt_map.get(prompt_id, payload)
        reference_text = references.get(prompt_id, {}).get("reference") or build_user_input(entity_type, prompt)
        retrieved_contexts = response.get("retrieved_sources") or []
        validation_issues = response.get("validation_issues") or []

        sample = {
            "id": row["id"],
            "prompt_id": prompt_id,
            "entity_type": entity_type,
            "condition": row["condition"],
            "user_input": build_user_input(entity_type, prompt),
            "response": render_parsed_output(parsed, entity_type),
            "reference": reference_text,
            "retrieved_contexts": retrieved_contexts,
            "rubric_rules_fit": row.get("rules_fit", ""),
            "rubric_sense": row.get("sense", ""),
            "rubric_style": row.get("style", ""),
            "validation_issues": validation_issues,
        }
        samples.append(sample)
    return samples


def build_judge_models() -> tuple[LangchainLLMWrapper, LangchainEmbeddingsWrapper]:
    api_key = os.getenv("RAGAS_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set OPENAI_API_KEY or RAGAS_OPENAI_API_KEY before running RAGAS evaluation.")

    base_url = os.getenv("RAGAS_OPENAI_BASE_URL") or None
    llm_model = os.getenv("RAGAS_EVAL_MODEL", "gpt-4o-mini")
    embedding_model = os.getenv("RAGAS_EMBED_MODEL", "text-embedding-3-small")

    llm = ChatOpenAI(model=llm_model, temperature=0, api_key=api_key, base_url=base_url)
    embeddings = OpenAIEmbeddings(model=embedding_model, api_key=api_key, base_url=base_url)
    return LangchainLLMWrapper(llm), LangchainEmbeddingsWrapper(embeddings)


def evaluate_samples(samples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    llm, embeddings = build_judge_models()
    metrics = [
        Faithfulness(llm=llm),
        AnswerRelevancy(llm=llm, embeddings=embeddings),
        ContextPrecision(llm=llm),
        ContextRecall(llm=llm),
        AnswerCorrectness(llm=llm, embeddings=embeddings),
    ]
    dataset = EvaluationDataset.from_list(samples)
    result = evaluate(dataset=dataset, metrics=metrics, raise_exceptions=False, show_progress=True)
    frame = result.to_pandas()
    per_sample = frame.to_dict(orient="records")

    by_condition: dict[str, dict[str, list[float]]] = {}
    metric_keys = [metric.name for metric in metrics]
    for sample, scored in zip(samples, per_sample):
        condition = sample["condition"]
        bucket = by_condition.setdefault(condition, {key: [] for key in metric_keys})
        for key in metric_keys:
            value = scored.get(key)
            if isinstance(value, (int, float)):
                bucket[key].append(float(value))

    summary_by_condition = {}
    for condition, metric_values in by_condition.items():
        summary_by_condition[condition] = {}
        for key, values in metric_values.items():
            summary_by_condition[condition][key] = {
                "mean": round(mean(values), 4) if values else None,
                "min": round(min(values), 4) if values else None,
                "max": round(max(values), 4) if values else None,
                "n": len(values),
            }

    overall = {}
    for key in metric_keys:
        values = [float(row[key]) for row in per_sample if isinstance(row.get(key), (int, float))]
        overall[key] = {
            "mean": round(mean(values), 4) if values else None,
            "min": round(min(values), 4) if values else None,
            "max": round(max(values), 4) if values else None,
            "n": len(values),
        }

    summary = {
        "status": "ok",
        "metric_names": metric_keys,
        "sample_count": len(samples),
        "overall": overall,
        "by_condition": summary_by_condition,
        "notes": [
            "RAGAS metrics complement but do not replace the manual rules-fit rubric.",
            "Answer correctness uses benchmark reference texts rather than full gold-standard sheets.",
            "Context metrics are most meaningful for the rag and validated_iterative_rag conditions.",
        ],
    }
    return per_sample, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RAGAS scoring against an existing benchmark run.")
    parser.add_argument("run_dir", help="Path to backend/eval/results/run_YYYYMMDD_HHMMSS")
    parser.add_argument("--prompts", default=str(DEFAULT_PROMPTS), help="Prompt set JSON used to create the benchmark")
    parser.add_argument("--references", default=str(DEFAULT_REFERENCES), help="Reference text JSON keyed by prompt_id")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    prompts_path = Path(args.prompts).resolve()
    references_path = Path(args.references).resolve()

    if not run_dir.exists():
        raise SystemExit(f"Run directory not found: {run_dir}")

    samples = build_dataset_rows(run_dir, prompts_path, references_path)
    dataset_preview_path = run_dir / "ragas_dataset_preview.json"
    with dataset_preview_path.open("w", encoding="utf-8") as handle:
        json.dump(samples, handle, indent=2)

    try:
        per_sample, summary = evaluate_samples(samples)
    except Exception as exc:
        summary = {
            "status": "not_configured",
            "error": str(exc),
            "sample_count": len(samples),
            "dataset_preview": str(dataset_preview_path),
            "notes": [
                "RAGAS is installed, but an evaluator model is not configured.",
                "Set OPENAI_API_KEY or RAGAS_OPENAI_API_KEY before running this script.",
                "The dataset preview file is still useful for dissertation documentation and auditability.",
            ],
        }
        per_sample = []

    with (run_dir / "ragas_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    with (run_dir / "ragas_per_sample.json").open("w", encoding="utf-8") as handle:
        json.dump(per_sample, handle, indent=2)

    print(run_dir / "ragas_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
