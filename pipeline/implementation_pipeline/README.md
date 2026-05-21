# Implementation Pipeline

This subproject builds the manual review queue for bank blockchain
implementation evidence from LexisNexis PDF exports.

The workflow has three main stages:

1. Parse source PDFs into article-level records.
2. Match focal-bank names and aliases inside each article.
3. Score article and sentence evidence and write a ranked review queue.

## Main Files

- `pipeline/implementation_pipeline/config/banks.json`
  Bank list and alias dictionary used in the retrieval and scoring steps.
- `pipeline/implementation_pipeline/src/parsing.py`
  Parses LexisNexis PDF exports into article records and Business Wire
  sub-articles.
- `pipeline/implementation_pipeline/src/scoring.py`
  Scores article-level and sentence-level implementation evidence.
- `pipeline/implementation_pipeline/src/review_queue_workflow.py`
  Runs the full parsing and scoring workflow and writes run outputs.
- `pipeline/implementation_pipeline/src/run_review_queue.py`
  Command-line entrypoint for building named review-queue runs.
- `pipeline/implementation_pipeline/tests/test_review_queue.py`
  Local regression checks for parsing and scoring behavior.

## Expected Local Data Layout

```text
pipeline/implementation_pipeline/
|-- config/
|-- data/
|   |-- phase_a/
|   |   |-- american_banker/
|   |   |-- pr_newswire/
|   |   `-- business_wire/
|   `-- phase_b/
|       `-- web_discovery/
|-- results/
|-- runs/
|-- src/
`-- tests/
```

The current workflow reads Phase A source files from
`pipeline/implementation_pipeline/data/phase_a/` and writes the active working
tree under `pipeline/implementation_pipeline/results/`.

The `phase_b/` folder is kept for follow-up discovery material, but the current
command-line runner builds the review queue from the Phase A corpus.

## Installation

Use Python 3.11+.

```bash
cd pipeline/implementation_pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

## Environment

Copy `.env.example` to `.env` if you want local overrides in your editor or
shell.

Supported environment variables:

- `IMPLEMENTATION_DATA_DIR`
- `IMPLEMENTATION_BANK_CONFIG`
- `IMPLEMENTATION_PIPELINE_OUT_ROOT`
- `IMPLEMENTATION_RUNS_ROOT`
- `IMPLEMENTATION_REVIEW_COUNT`
- `PYTHONDONTWRITEBYTECODE`

## How To Run

From `pipeline/implementation_pipeline/`:

```bash
.venv/bin/python src/run_review_queue.py build
```

To build `results/` and write a named run snapshot:

```bash
.venv/bin/python src/run_review_queue.py run full_v4
```

To restrict the run to selected sources:

```bash
.venv/bin/python src/run_review_queue.py build --sources american_banker pr_newswire
```

To shrink the run for local checks:

```bash
.venv/bin/python src/run_review_queue.py build --max-files-per-source 10 --review-count 50
```

To archive an existing `results/` tree without rebuilding it:

```bash
.venv/bin/python src/run_review_queue.py archive full_v4
```

## Run Outputs

The active working tree under `pipeline/implementation_pipeline/results/`
contains:

- `article_review_queue.csv`
- `sentence_evidence.csv`
- `parse_failures.csv`
- `run_summary.json`
- `articles.jsonl`
- `bw_segmentation_review.csv`
- `business_wire_segments/`

Each archived snapshot under `pipeline/implementation_pipeline/runs/` stores a
copy of the same output tree plus:

- `run_metadata.json`
- `run.log`
- `00_inputs/`
