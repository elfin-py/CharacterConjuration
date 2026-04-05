#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
from collections import Counter, defaultdict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BACKEND = "http://127.0.0.1:8000"
DEFAULT_CONDITIONS = ["no_rag", "rag", "validated_iterative_rag"]
FAILURE_COLUMNS = [
    "failure_invalid_combo",
    "failure_derived_stats",
    "failure_spell_errors",
    "failure_proficiency_mismatch",
    "failure_schema_omission",
    "failure_weak_grounding",
    "failure_generic_narrative",
]
SCORE_COLUMNS = ["sense", "rules_fit", "style"]


def now_stamp():
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")



def load_prompts(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)



def post_json(url: str, payload: dict) -> tuple[int, dict | str]:
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=180) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body)
            except Exception:
                return resp.status, body
    except HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except URLError as e:
        return 0, str(e)



def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)



def empty_scores():
    row = {"sense": "", "rules_fit": "", "style": "", "failure_types": "", "notes": ""}
    for col in FAILURE_COLUMNS:
        row[col] = ""
    return row


def join_items(value):
    if isinstance(value, list):
        return "; ".join(str(v) for v in value if str(v).strip())
    return str(value or "")


def count_items(value):
    if isinstance(value, list):
        return len([v for v in value if str(v).strip()])
    text = str(value or "").strip()
    if not text:
        return 0
    return len([part for part in text.split(";") if part.strip()])


def numeric_stats(rows, group_key=None):
    grouped = defaultdict(list)
    if group_key is None:
        grouped["overall"] = rows
    else:
        for row in rows:
            grouped[row.get(group_key, "unknown")].append(row)

    out = {}
    for group, items in grouped.items():
        out[group] = {}
        for col in SCORE_COLUMNS:
            vals = []
            for row in items:
                try:
                    vals.append(float(row.get(col, "")))
                except Exception:
                    pass
            out[group][col] = {
                "mean": round(sum(vals) / len(vals), 2) if vals else None,
                "min": min(vals) if vals else None,
                "max": max(vals) if vals else None,
                "n": len(vals),
            }
    return out



def failure_counts(rows, group_key="condition"):
    grouped = defaultdict(Counter)
    for row in rows:
        group = row.get(group_key, "unknown")
        for col in FAILURE_COLUMNS:
            value = str(row.get(col, "")).strip().lower()
            if value in {"1", "true", "yes", "y", "x"}:
                grouped[group][col] += 1
    return {group: dict(counter) for group, counter in grouped.items()}



def build_payload(entity_type: str, prompt: dict, condition: str) -> dict:
    return {
        "entity_type": entity_type,
        "roll_mode": prompt.get("roll_mode", "auto"),
        "experimental_mode": condition,
        "race": prompt.get("race"),
        "dnd_class": prompt.get("dnd_class"),
        "level": prompt.get("level"),
        "alignment": prompt.get("alignment"),
        "concept": prompt.get("concept"),
        "gender": prompt.get("gender"),
        "age_group": prompt.get("age_group"),
        "manual_rolls": prompt.get("manual_rolls"),
        "ability_assignment": prompt.get("ability_assignment"),
    }



def artifact_name(entity_type: str, index: int, condition: str) -> str:
    return f"{entity_type}_{index:02d}_{condition}"



def main():
    parser = argparse.ArgumentParser(description="Run comparative RAG benchmark and export dissertation-ready CSV.")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, help="Backend base URL")
    parser.add_argument(
        "--prompts",
        default="backend/eval/dissertation_prompts.json",
        help="Path to prompt set JSON",
    )
    parser.add_argument("--out", default="", help="Output directory (default backend/eval/results/run_TIMESTAMP)")
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=DEFAULT_CONDITIONS,
        help="Experimental conditions to run",
    )
    args = parser.parse_args()

    prompts = load_prompts(args.prompts)
    conditions = [c for c in args.conditions if c in DEFAULT_CONDITIONS]
    if not conditions:
        raise SystemExit("No valid conditions supplied.")

    stamp = now_stamp()
    out_dir = args.out or os.path.join("backend", "eval", "results", f"run_{stamp}")
    ensure_dir(out_dir)

    results = []
    for entity_type, items in prompts.items():
        for i, item in enumerate(items, start=1):
            for condition in conditions:
                payload = build_payload(entity_type, item, condition)
                status, data = post_json(f"{args.backend}/generate_character", payload)
                row = {
                    "id": artifact_name(entity_type, i, condition),
                    "prompt_id": f"{entity_type}_{i:02d}",
                    "entity_type": entity_type,
                    "condition": condition,
                    "prompt": json.dumps(payload, ensure_ascii=False),
                    "timestamp": dt.datetime.now().isoformat(),
                    "status": status,
                    "success": status == 200,
                    "name": "",
                    "model": "",
                    "attempt_count": "",
                    "validation_issues": "",
                    "validation_issue_count": "",
                    "model_validation_issues": "",
                    "model_validation_issue_count": "",
                    "correction_notes": "",
                    "correction_count": "",
                    "retrieved_sources_count": "",
                    "raw_output_path": "",
                    "parsed_output_path": "",
                }
                row.update(empty_scores())

                artifact = {
                    "prompt_id": row["prompt_id"],
                    "entity_type": entity_type,
                    "condition": condition,
                    "payload": payload,
                    "status": status,
                    "response": data,
                }

                if status == 200 and isinstance(data, dict):
                    parsed = data.get("parsed") or data.get("sheet_json") or {}
                    row["name"] = parsed.get("name", "")
                    row["model"] = data.get("used_model") or data.get("model") or ""
                    row["attempt_count"] = data.get("attempt_count", "")
                    row["validation_issues"] = join_items(data.get("validation_issues"))
                    row["validation_issue_count"] = count_items(data.get("validation_issues"))
                    row["model_validation_issues"] = join_items(data.get("model_validation_issues"))
                    row["model_validation_issue_count"] = count_items(data.get("model_validation_issues"))
                    row["correction_notes"] = join_items(data.get("correction_notes"))
                    row["correction_count"] = count_items(data.get("correction_notes"))
                    row["retrieved_sources_count"] = len(data.get("retrieved_sources") or [])
                    raw_output_path = os.path.join(out_dir, f"{row['id']}_raw.txt")
                    parsed_output_path = os.path.join(out_dir, f"{row['id']}_parsed.json")
                    with open(raw_output_path, "w", encoding="utf-8") as f:
                        f.write(str(data.get("answer") or ""))
                    with open(parsed_output_path, "w", encoding="utf-8") as f:
                        json.dump(parsed, f, indent=2)
                    row["raw_output_path"] = raw_output_path
                    row["parsed_output_path"] = parsed_output_path
                else:
                    row["failure_types"] = "request_failed"
                    row["notes"] = str(data)[:2000]

                results.append(row)
                with open(os.path.join(out_dir, f"{row['id']}.json"), "w", encoding="utf-8") as f:
                    json.dump(artifact, f, indent=2)
                time.sleep(0.2)

    csv_path = os.path.join(out_dir, "results.csv")
    fieldnames = [
        "id",
        "prompt_id",
        "entity_type",
        "condition",
        "prompt",
        "timestamp",
        "status",
        "success",
        "name",
        "model",
        "attempt_count",
        "validation_issues",
        "validation_issue_count",
        "model_validation_issues",
        "model_validation_issue_count",
        "correction_notes",
        "correction_count",
        "retrieved_sources_count",
        "raw_output_path",
        "parsed_output_path",
        "sense",
        "rules_fit",
        "style",
        "failure_types",
        *FAILURE_COLUMNS,
        "notes",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)

    summary = {
        "run_id": stamp,
        "backend": args.backend,
        "results_dir": out_dir,
        "conditions": conditions,
        "counts": {
            "total": len(results),
            "success": sum(1 for row in results if row["success"]),
            "failure": sum(1 for row in results if not row["success"]),
        },
        "stats_overall": numeric_stats(results),
        "stats_by_condition": numeric_stats(results, group_key="condition"),
        "failure_counts_by_condition": failure_counts(results, group_key="condition"),
    }
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote {len(results)} results to {out_dir}")
    print(f"CSV: {csv_path}")
    print(f"Summary: {os.path.join(out_dir, 'summary.json')}")


if __name__ == "__main__":
    sys.exit(main())
