# Comparative RAG Benchmark

This evaluation package supports the dissertation ablation:
- `no_rag`
- `rag`
- `validated_iterative_rag`

The default dissertation run uses `10 prompts x 3 conditions = 30 outputs` with this mix:
- `6` player characters
- `2` NPCs
- `2` enemies

## Files

- `backend/eval/dissertation_prompts.json` - reduced 10-prompt benchmark set
- `backend/eval/prompts.json` - larger prompt pool retained from earlier prototype work
- `backend/eval/benchmark_run.py` - runs all requested conditions and writes artifacts
- `backend/eval/summarize_results.py` - computes condition-level score and failure summaries from the scored CSV

## Output structure

Each run writes:
- `backend/eval/results/run_YYYYMMDD_HHMMSS/`
  - `results.csv`
  - `summary.json`
  - `condition_summary.json` (after running `summarize_results.py`)
  - `{entity}_{NN}_{condition}.json` - request/response artifact
  - `{entity}_{NN}_{condition}_raw.txt` - raw model output
  - `{entity}_{NN}_{condition}_parsed.json` - parsed structured output

## Run the benchmark

Start the backend, then run:

```bash
python backend/eval/benchmark_run.py
```

Optional overrides:

```bash
python backend/eval/benchmark_run.py \
  --backend http://127.0.0.1:8000 \
  --prompts backend/eval/dissertation_prompts.json \
  --out backend/eval/results/run_custom \
  --conditions no_rag rag validated_iterative_rag
```

## Manual scoring columns

Fill these in `results.csv` after the run:
- `sense` (1-5)
- `rules_fit` (1-5)
- `style` (1-5)
- `failure_types` (comma-separated notes)
- `notes`

Fixed failure taxonomy columns:
- `failure_invalid_combo`
- `failure_derived_stats`
- `failure_spell_errors`
- `failure_proficiency_mismatch`
- `failure_schema_omission`
- `failure_weak_grounding`
- `failure_generic_narrative`

Use `1`/`true` when the failure is present.

## Aggregate scored results

After manual scoring:

```bash
python backend/eval/summarize_results.py backend/eval/results/run_YYYYMMDD_HHMMSS/results.csv
```

This writes `condition_summary.json` with:
- mean/min/max for `sense`, `rules_fit`, and `style` by condition
- failure counts by condition

## Notes for the dissertation

- Use `validated iterative RAG` as the dissertation term for the third condition.
- Keep the existing prototype dataset separate from this final comparative run.
- The annotated human-authored character sheet should be treated as a supporting case study rather than part of the main benchmark CSV.
