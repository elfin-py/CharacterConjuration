# Character Conjuration

Character Conjuration is a hybrid D&D 5e generation app that combines:

- handbook-derived retrieval,
- structured LLM generation,
- deterministic validation and correction,
- and downstream rendering for player characters, NPCs, and enemies.

The project has two main parts:

- `backend/` - a FastAPI service that retrieves rule context, generates structured outputs, validates them, and exports sheets/stat blocks
- `characterconjuration/` - a Next.js frontend for building and viewing generated entities

## Repository layout

```text
backend/                  FastAPI app, validation logic, retrieval index, evaluation scripts
characterconjuration/     Next.js frontend
report/                   Dissertation/report sources
```

Useful backend files:

- `backend/app.py` - main FastAPI application
- `backend/rules_data.py` - rule helpers, validation, recomputation logic
- `backend/fill_pdf.py` - official 5e sheet filling
- `backend/build_index.py` - rebuilds the retrieval index from markdown rule files
- `backend/tests/test_rules_and_pdf.py` - implemented backend unit tests
- `backend/eval/` - benchmark and RAGAS evaluation scripts
- `backend/.env.example` - example environment configuration

Submission-critical runtime assets:

- `backend/data/split_md/` - handbook-derived markdown corpus used for retrieval, index rebuilding, and markdown fallback retrieval
- `backend/data/pdf/5E_CharacterSheet_Fillable.pdf` - sheet template used for official PDF export

## Prerequisites

- Python 3.11+ recommended
- Node.js 18+ recommended
- npm
- A Hugging Face access token for model calls

## Setup

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd CharacterConjuration
```

### 2. Set up the backend

Create and activate a virtual environment:

```bash
python3 -m venv backend/venv
source backend/venv/bin/activate
```

Install the backend dependencies:

```bash
pip install -r backend/requirements.txt
```

For a fuller local development setup, including the supplementary evaluation tooling, install:

```bash
pip install -r backend/requirements-dev.txt
```

Copy `backend/.env.example` to `backend/.env` and fill in your token:

```bash
cp backend/.env.example backend/.env
```

Notes:

- `HF_TOKEN` is required. The backend raises an error if it is missing.
- `HF_MODEL` and `HF_MODEL_CANDIDATES` are optional overrides. The backend has defaults.
- Do not commit a real `backend/.env` file with live credentials.

### 3. Prepare retrieval data

The repository also includes:

- `backend/data/pdf/5E_CharacterSheet_Fillable.pdf` - official 5e sheet template used for PDF export
- `backend/data/split_md/` - handbook-derived markdown used for retrieval and index rebuilding

The submitted repository retains the handbook-derived markdown corpus because the dissertation discusses that corpus directly and the backend can fall back to it if a serialized vector index is absent or unusable.

If you want a local vector index, or if you update the handbook-derived markdown files under `backend/data/split_md`, rebuild the index:

```bash
cd backend
source venv/bin/activate
python build_index.py
```

If the vector index cannot be loaded, the backend will try to fall back to a simpler markdown retriever rather than failing immediately.

For this submission repository, the markdown corpus is intentionally kept in the repo so that the retrieval pipeline described in the dissertation can be inspected directly.

### 4. Start the backend

From the `backend/` directory:

```bash
cd backend
source venv/bin/activate
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

### 5. Set up the frontend

In a second terminal:

```bash
cd characterconjuration
npm install
npm run dev
```

The frontend runs on:

- `http://127.0.0.1:3000`

The Next.js API routes proxy requests to the backend at `http://127.0.0.1:8000`, so the backend must be running first.

## How to use the app

### Main generation flow

1. Open `http://127.0.0.1:3000`
2. Choose a builder type:
   - `Player Character`
   - `Enemy / Monster`
   - `NPC`
3. Fill in the prompt fields
4. Click `Generate`
5. Review the generated result on the detail page

### Creating a player character

For player characters, you can provide:

- race
- class
- level
- alignment
- concept
- optional gender and age group
- ability score mode:
  - `Auto roll`
  - `Standard array`
  - `Point buy`
  - `Manual input`

After generation, the detail page shows:

- core identity fields
- abilities
- AC / HP / speed
- flavour text
- raw JSON

You can also download:

- a filled official 5e character sheet PDF

### Creating an enemy

For enemies, you can provide:

- creature type
- challenge or difficulty
- environment
- tactics
- general concept text

After generation, the detail page shows:

- enemy basics
- flavour
- raw JSON
- a generated stat-block style output

You can also download:

- a generated stat block PDF

### Creating an NPC

For NPCs, you can provide:

- role
- demeanor
- connection to the party
- general concept text

NPC outputs are lighter-weight than player-character sheets and are intended as usable summaries rather than full character builds.

## App pages

- `/` - main builder
- `/detail` - latest generated entity view
- `/eval` - latest benchmark and RAGAS summary view

## Backend API endpoints

Main endpoints exposed by the FastAPI app:

- `POST /generate_character` - generate a character, NPC, or enemy
- `POST /fill_sheet` - fill a sheet PDF
- `POST /fill_sheet_official` - fill the official 5e sheet
- `POST /fill_statblock` - build an enemy stat block export
- `GET /health` - health check
- `GET /eval/latest` - latest evaluation summary
- `POST /eval/run_ragas` - run RAGAS against the latest benchmark artifacts

## Running tests

Implemented backend unit tests live in:

- `backend/tests/test_rules_and_pdf.py`

Run them with:

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
python -m unittest tests/test_rules_and_pdf.py
```

These tests cover selected deterministic validation and PDF export behaviour, including:

- hit point recomputation
- armour class recomputation
- skill normalisation
- saving throw validation
- spell validation
- PDF filling

## Running the benchmark

Start the backend first, then run:

```bash
cd backend
source venv/bin/activate
python eval/benchmark_run.py
```

The default dissertation benchmark runs:

- `no_rag`
- `rag`
- `validated_iterative_rag`

against the reduced prompt set in:

- `backend/eval/dissertation_prompts.json`

Results are written under:

- `backend/eval/results/run_YYYYMMDD_HHMMSS/`

For more detail, see:

- `backend/eval/README.md`

## Requirements files

- `backend/requirements.txt` - pinned runtime dependencies for the FastAPI app
- `backend/requirements-dev.txt` - runtime dependencies plus evaluation/dev extras
- `backend/requirements-eval.txt` - supplementary evaluation-only packages used for RAGAS workflows

## Troubleshooting

### Backend says `HF_TOKEN not set`

Add a valid Hugging Face token to:

- `backend/.env`

### Frontend says backend unavailable

Check that:

- the FastAPI server is running on `127.0.0.1:8000`
- the frontend is running on `127.0.0.1:3000`
- no firewall or port conflict is blocking local requests

### Retrieval index fails to load

The backend will attempt a markdown fallback retriever. If you want the main vector index back, rebuild it with:

```bash
cd backend
source venv/bin/activate
python build_index.py
```

### PDF export fails

Check that the official template exists:

- `backend/data/pdf/5E_CharacterSheet_Fillable.pdf`

## Notes

- This is a research project, not a complete symbolic D&D 5e rules engine.
- Validation is selective rather than exhaustive.
- Retrieval and correction improve reliability, but generated outputs should still be inspected before use in play.
- `backend/.env` is intentionally excluded from the repository; use `backend/.env.example` instead.
