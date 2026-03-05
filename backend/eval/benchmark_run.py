#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


DEFAULT_BACKEND = "http://127.0.0.1:8000"


def now_stamp():
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def load_prompts(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def post_json(url: str, payload: dict) -> tuple[int, dict | str]:
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=120) as resp:
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
    return {"sense": "", "rules_fit": "", "style": "", "failure_types": "", "notes": ""}


def summary_stats(rows):
    def numeric(col):
        vals = []
        for r in rows:
            v = r.get(col, "")
            try:
                vals.append(float(v))
            except Exception:
                pass
        return vals

    stats = {}
    for col in ["sense", "rules_fit", "style"]:
        vals = numeric(col)
        if vals:
            stats[col] = {
                "mean": round(sum(vals) / len(vals), 2),
                "min": min(vals),
                "max": max(vals),
                "n": len(vals),
            }
        else:
            stats[col] = {"mean": None, "min": None, "max": None, "n": 0}
    return stats


def build_payload(entity_type: str, prompt: dict) -> dict:
    payload = {
        "entity_type": entity_type,
        "roll_mode": "auto",
        "race": prompt.get("race"),
        "dnd_class": prompt.get("dnd_class"),
        "level": prompt.get("level"),
        "alignment": prompt.get("alignment"),
        "concept": prompt.get("concept"),
    }
    return payload


def main():
    parser = argparse.ArgumentParser(description="Run 10-sample benchmark and export CSV.")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, help="Backend base URL")
    parser.add_argument("--prompts", default="backend/eval/prompts.json", help="Path to prompts.json")
    parser.add_argument("--out", default="", help="Output directory (default backend/eval/results/run_TIMESTAMP)")
    args = parser.parse_args()

    prompts = load_prompts(args.prompts)
    stamp = now_stamp()
    out_dir = args.out or os.path.join("backend", "eval", "results", f"run_{stamp}")
    ensure_dir(out_dir)

    results = []
    for entity_type, items in prompts.items():
        for i, item in enumerate(items, start=1):
            payload = build_payload(entity_type, item)
            status, data = post_json(f"{args.backend}/generate_character", payload)
            row = {
                "id": f"{entity_type}_{i:02d}",
                "entity_type": entity_type,
                "prompt": json.dumps(payload, ensure_ascii=False),
                "timestamp": dt.datetime.now().isoformat(),
                "status": status,
                "success": status == 200,
            }
            row.update(empty_scores())
            row["failure_types"] = ""
            row["notes"] = ""

            if status == 200 and isinstance(data, dict):
                row["name"] = (data.get("parsed") or {}).get("name")
                row["model"] = data.get("used_model") or data.get("model") or ""
            else:
                row["name"] = ""
                row["model"] = ""
                row["failure_types"] = "request_failed"
                row["notes"] = str(data)[:2000]

            results.append(row)
            with open(os.path.join(out_dir, f"{row['id']}.json"), "w", encoding="utf-8") as f:
                json.dump({"payload": payload, "response": data, "status": status}, f, indent=2)
            time.sleep(0.2)

    csv_path = os.path.join(out_dir, "results.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "id",
            "entity_type",
            "prompt",
            "timestamp",
            "status",
            "success",
            "name",
            "model",
            "sense",
            "rules_fit",
            "style",
            "failure_types",
            "notes",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    summary = {
        "run_id": stamp,
        "backend": args.backend,
        "results_dir": out_dir,
        "counts": {
            "total": len(results),
            "success": sum(1 for r in results if r["success"]),
            "failure": sum(1 for r in results if not r["success"]),
        },
        "stats": summary_stats(results),
    }
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote {len(results)} results to {out_dir}")
    print(f"CSV: {csv_path}")
    print(f"Summary: {os.path.join(out_dir, 'summary.json')}")


if __name__ == "__main__":
    sys.exit(main())
