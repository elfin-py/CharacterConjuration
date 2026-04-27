#!/usr/bin/env python3
import argparse
import csv
import json
import os
from collections import Counter, defaultdict

SCORE_COLUMNS = ["sense", "rules_fit", "style"]
FAILURE_COLUMNS = [
    "failure_invalid_combo",
    "failure_derived_stats",
    "failure_spell_errors",
    "failure_proficiency_mismatch",
    "failure_schema_omission",
    "failure_weak_grounding",
    "failure_generic_narrative",
]


def load_rows(path: str):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))



def score_summary(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.get("condition", "unknown")].append(row)

    summary = {}
    for condition, items in grouped.items():
        summary[condition] = {}
        for col in SCORE_COLUMNS:
            vals = []
            for item in items:
                try:
                    vals.append(float(item.get(col, "")))
                except Exception:
                    pass
            summary[condition][col] = {
                "mean": round(sum(vals) / len(vals), 2) if vals else None,
                "min": min(vals) if vals else None,
                "max": max(vals) if vals else None,
                "n": len(vals),
            }
    return summary



def failure_summary(rows):
    grouped = defaultdict(Counter)
    for row in rows:
        condition = row.get("condition", "unknown")
        for col in FAILURE_COLUMNS:
            value = str(row.get(col, "")).strip().lower()
            if value in {"1", "true", "yes", "y", "x"}:
                grouped[condition][col] += 1
    return {condition: dict(counter) for condition, counter in grouped.items()}



def main():
    parser = argparse.ArgumentParser(description="Summarize dissertation benchmark CSV results.")
    parser.add_argument("csv_path", help="Path to backend/eval/results/.../results.csv")
    parser.add_argument("--out", default="", help="Optional explicit output JSON path")
    args = parser.parse_args()

    rows = load_rows(args.csv_path)
    output = {
        "source_csv": args.csv_path,
        "score_summary_by_condition": score_summary(rows),
        "failure_counts_by_condition": failure_summary(rows),
    }

    out_path = args.out or os.path.join(os.path.dirname(args.csv_path), "condition_summary.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(out_path)


if __name__ == "__main__":
    main()
