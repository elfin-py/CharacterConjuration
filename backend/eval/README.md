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
- `backend/eval/large_scale_prompts.json` - explicit 30-prompt larger-scale benchmark set (10 character, 10 NPC, 10 enemy)
- `backend/eval/benchmark_run.py` - runs all requested conditions and writes artifacts
- `backend/eval/summarize_results.py` - computes condition-level score and failure summaries from the scored CSV
- `backend/eval/dissertation_references.json` - benchmark reference texts for RAGAS-assisted scoring
- `backend/eval/large_scale_references.json` - generated reference texts for the larger-scale prompt set
- `backend/eval/build_reference_texts.py` - generates simple reference texts from a prompt file
- `backend/eval/ragas_eval.py` - converts a saved run into a RAGAS dataset and scores it
- `backend/eval/analyze_ragas_alignment.py` - compares RAGAS metrics against manual rubric scores

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

For a larger supplementary run:

```bash
python backend/eval/benchmark_run.py \
  --backend http://127.0.0.1:8000 \
  --prompts backend/eval/large_scale_prompts.json \
  --out backend/eval/results/run_large_scale \
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

To keep cost and latency down, you can run only the cheaper retrieval-oriented metrics:

```bash
python backend/eval/ragas_eval.py backend/eval/results/run_YYYYMMDD_HHMMSS \
  --metrics answer_relevancy context_precision context_recall
```

For the larger prompt set, point RAGAS at the matching references:

```bash
python backend/eval/ragas_eval.py backend/eval/results/run_large_scale \
  --prompts backend/eval/large_scale_prompts.json \
  --references backend/eval/large_scale_references.json
```

This writes:
- `ragas_dataset_preview.json`
- `ragas_summary.json`
- `ragas_per_sample.json`

Expected environment:
- preferred: `GOOGLE_API_KEY`, `GEMINI_API_KEY`, or `RAGAS_GOOGLE_API_KEY`
- fallback: `OPENAI_API_KEY` or `RAGAS_OPENAI_API_KEY`
- alternative: `HF_TOKEN` or `RAGAS_HF_TOKEN` with `RAGAS_EVAL_PROVIDER=hf`
- optional `RAGAS_EVAL_PROVIDER` (`google` / `gemini` / `openai`)
- optional `RAGAS_EVAL_MODEL`
- optional `RAGAS_EMBED_MODEL`
- optional `RAGAS_OPENAI_BASE_URL` for compatible OpenAI-style providers
- optional `RAGAS_HF_BASE_URL` (defaults to `https://router.huggingface.co/v1`)

Default evaluator models:
- Gemini: `gemini-2.5-flash` + `gemini-embedding-001`
- OpenAI: `gpt-4o-mini` + `text-embedding-3-small`
- Hugging Face: `Qwen/Qwen2.5-7B-Instruct-1M:hf-inference` + `intfloat/multilingual-e5-large`

Example Hugging Face configuration:

```bash
export RAGAS_EVAL_PROVIDER=hf
export HF_TOKEN=...
export RAGAS_EVAL_MODEL=Qwen/Qwen2.5-7B-Instruct-1M:hf-inference
export RAGAS_EMBED_MODEL=intfloat/multilingual-e5-large
```

The implemented RAGAS metrics are:
- `faithfulness`
- `answer_relevancy`
- `context_precision`
- `context_recall`
- `answer_correctness`

Use these as retrieval diagnostics. They do not replace the manual `rules_fit` score for D&D legality.

## Compare RAGAS to the manual rubric

Once a run has both:
- manual `sense`, `rules_fit`, and `style` scores
- `ragas_dataset_preview.json` and `ragas_per_sample.json`

run:

```bash
python backend/eval/analyze_ragas_alignment.py backend/eval/results/run_YYYYMMDD_HHMMSS
```

This writes `ragas_alignment_summary.json` with:
- Pearson and Spearman correlations between each manual rubric dimension and each RAGAS metric
- per-condition breakdowns

Interpret these as calibration diagnostics only. The intended dissertation use is:
- manual rubric = domain-valid human evaluation
- deterministic validation = rule-specific mechanical checking
- RAGAS = retrieval/grounding diagnostics at scale