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
- `backend/eval/dissertation_references.json` - benchmark reference texts for RAGAS-assisted scoring
- `backend/eval/ragas_eval.py` - converts a saved run into a RAGAS dataset and scores it

## Output structure

Each run writes:
- `backend/eval/results/run_YYYYMMDD_HHMMSS/`
  - `results.csv`
  - `summary.json`
  - `condition_summary.json` (after running `summarize_results.py`)
  - `ragas_dataset_preview.json` (after running `ragas_eval.py`)
  - `ragas_summary.json` (after running `ragas_eval.py`)
  - `ragas_per_sample.json` (after running `ragas_eval.py`)
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

## RAGAS-assisted scoring

Install the evaluation-only dependencies if they are not already present:

```bash
pip install -r backend/requirements-eval.txt
```

Then run:

```bash
python backend/eval/ragas_eval.py backend/eval/results/run_YYYYMMDD_HHMMSS
```

This writes:
- `ragas_dataset_preview.json`
- `ragas_summary.json`
- `ragas_per_sample.json`

Expected environment:
- `OPENAI_API_KEY` or `RAGAS_OPENAI_API_KEY`
- optional `RAGAS_EVAL_MODEL` (defaults to `gpt-4o-mini`)
- optional `RAGAS_EMBED_MODEL` (defaults to `text-embedding-3-small`)
- optional `RAGAS_OPENAI_BASE_URL` for compatible providers

The implemented RAGAS metrics are:
- `faithfulness`
- `answer_relevancy`
- `context_precision`
- `context_recall`
- `answer_correctness`

Use these as retrieval diagnostics. They do not replace the manual `rules_fit` score for D&D legality.

## Notes for the dissertation

- Use `validated iterative RAG` as the dissertation term for the third condition.
- Keep the existing prototype dataset separate from this final comparative run.
- The annotated human-authored character sheet should be treated as a supporting case study rather than part of the main benchmark CSV.
