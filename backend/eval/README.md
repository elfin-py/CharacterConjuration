# Benchmark Runner

Runs 10 sample conjurations for **character**, **npc**, and **enemy** and writes:
- `backend/eval/results/run_YYYYMMDD_HHMMSS/`
  - `results.csv` (manual scoring fields included)
  - `summary.json` (mean/range stats for filled scores)
  - `{entity}_{NN}.json` (raw request/response)

## Usage

Start the backend, then:

```bash
python backend/eval/benchmark_run.py
```

Optional overrides:

```bash
python backend/eval/benchmark_run.py --backend http://127.0.0.1:8000 --prompts backend/eval/prompts.json --out backend/eval/results/run_custom
```

## Scoring

Fill the following columns in `results.csv`:
- `sense` (1–5)
- `rules_fit` (1–5)
- `style` (1–5)
- `failure_types` (comma-separated)
- `notes`

Re-run to generate a new folder with the same structure.
