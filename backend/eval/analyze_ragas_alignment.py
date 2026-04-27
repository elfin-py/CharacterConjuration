#!/usr/bin/env python3
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

MANUAL_COLUMNS = ["sense", "rules_fit", "style"]
DEFAULT_RAGAS_COLUMNS = [
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "answer_correctness",
]


def load_csv(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def to_float(value):
    try:
        value = float(value)
    except Exception:
        return None
    if math.isfinite(value):
        return value
    return None


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def rank(values):
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def spearman(xs, ys):
    if len(xs) < 2:
        return None
    return pearson(rank(xs), rank(ys))


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare manual rubric scores to RAGAS metrics for a benchmark run.")
    parser.add_argument("run_dir", help="Path to backend/eval/results/run_*")
    parser.add_argument(
        "--csv",
        default="results_manual_scored.csv",
        help="Scored CSV filename inside the run dir (default: results_manual_scored.csv)",
    )
    parser.add_argument(
        "--out",
        default="ragas_alignment_summary.json",
        help="Output JSON filename inside the run dir",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    scored_rows = load_csv(run_dir / args.csv)
    dataset_rows = load_json(run_dir / "ragas_dataset_preview.json")
    ragas_rows = load_json(run_dir / "ragas_per_sample.json")

    if len(dataset_rows) != len(ragas_rows):
        raise SystemExit("ragas_dataset_preview.json and ragas_per_sample.json row counts do not match")

    manual_by_id = {row["id"]: row for row in scored_rows}
    merged = []
    for dataset_row, ragas_row in zip(dataset_rows, ragas_rows):
        row_id = dataset_row["id"]
        manual = manual_by_id.get(row_id)
        if not manual:
            continue
        combined = {
            "id": row_id,
            "condition": dataset_row.get("condition", ""),
        }
        for key in MANUAL_COLUMNS:
            combined[key] = to_float(manual.get(key))
        for key in DEFAULT_RAGAS_COLUMNS:
            combined[key] = to_float(ragas_row.get(key))
        merged.append(combined)

    def summarize(items):
        result = {}
        for manual_key in MANUAL_COLUMNS:
            result[manual_key] = {}
            for ragas_key in DEFAULT_RAGAS_COLUMNS:
                pairs = [
                    (row[manual_key], row[ragas_key])
                    for row in items
                    if row.get(manual_key) is not None and row.get(ragas_key) is not None
                ]
                xs = [p[0] for p in pairs]
                ys = [p[1] for p in pairs]
                result[manual_key][ragas_key] = {
                    "n": len(pairs),
                    "pearson": round(pearson(xs, ys), 4) if pearson(xs, ys) is not None else None,
                    "spearman": round(spearman(xs, ys), 4) if spearman(xs, ys) is not None else None,
                }
        return result

    by_condition = defaultdict(list)
    for row in merged:
        by_condition[row["condition"]].append(row)

    output = {
        "run_dir": str(run_dir),
        "sample_count": len(merged),
        "overall": summarize(merged),
        "by_condition": {condition: summarize(items) for condition, items in by_condition.items()},
        "notes": [
            "These correlations are calibration diagnostics, not proof that RAGAS can replace manual D&D legality scoring.",
            "Low or unstable correlation is expected for rules-fit because RAGAS does not encode the D&D ruleset symbolically.",
            "Use this analysis to compare generic retrieval metrics against the manual rubric rather than as a learned evaluator.",
        ],
    }

    out_path = run_dir / args.out
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)

    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
