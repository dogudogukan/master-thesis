# Patent Pipeline

This subproject builds a bank-focused blockchain patent dataset from USPTO
PatentsView files.

The workflow has four main stages:

1. Preprocess raw PatentsView TSV.ZIP files into filtered Parquet files.
2. Apply the blockchain query and write the combined patent set.
3. Link extracted patents to assignees and then to the curated bank mapping.
4. Build the final bank-level summary tables.

## Main Files

- `pipeline/patent_pipeline/config/`
  Configuration for paths, selected columns, preprocessing options, and the
  blockchain query terms.
- `pipeline/patent_pipeline/src/database_preparation/preprocess_patents.py`
  Converts the raw PatentsView source files into filtered Parquet files.
- `pipeline/patent_pipeline/src/identification_of_blockchain_patents/extract_blockchain_patents.py`
  Builds the `Q1`, `Q2`, and `Q3` match sets and writes the extracted
  blockchain patent file.
- `pipeline/patent_pipeline/src/identification_of_blockchain_patents/extract_blockchain_assignees.py`
  Lists the assignees attached to the extracted blockchain patent set.
- `pipeline/patent_pipeline/src/identification_of_blockchain_patents/build_bank_patent_dataset.py`
  Builds the final patent-level bank dataset from the extracted blockchain
  patents and the curated mapping file.
- `pipeline/patent_pipeline/src/identification_of_blockchain_patents/build_bank_summary_tables.py`
  Builds the bank-level summary tables from the final patent-level dataset.
- `pipeline/patent_pipeline/src/run_patent_pipeline.py`
  Runs the pipeline into named snapshots and archives existing outputs.
- `pipeline/patent_pipeline/mapping/unique_assignees_bank_mapping.csv`
  Curated assignee-to-bank mapping used in the bank attribution step.

## Expected Local Data Layout

```text
pipeline/patent_pipeline/
|-- config/
|-- data/
|   |-- raw/
|   `-- processed/
|-- mapping/
|-- extra/
|-- results/
|-- runs/
|-- logs/
`-- src/
```

The current code expects:

- raw PatentsView files under `pipeline/patent_pipeline/data/raw/`
- processed Parquet files under `pipeline/patent_pipeline/data/processed/`
- the bank mapping file under `pipeline/patent_pipeline/mapping/`

The `extra/` folder is organized by source:

- `pipeline/patent_pipeline/extra/google_patents/`
- `pipeline/patent_pipeline/extra/sec/`
- `pipeline/patent_pipeline/extra/maintenance_fee_events/`
- `pipeline/patent_pipeline/extra/assignment/`

## Installation

Use Python 3.11+.

```bash
cd pipeline/patent_pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment

Copy `.env.example` to `.env` if you want local overrides in your editor or
shell.

Supported environment variables:

- `PATENT_DATA_DIR`
- `PATENT_PIPELINE_OUT_ROOT`
- `BANK_ASSIGNEE_MAPPING_CSV`
- `PREPROCESS_OVERWRITE`
- `PYTHONDONTWRITEBYTECODE`

## How To Run

From `pipeline/patent_pipeline/`:

```bash
.venv/bin/python src/database_preparation/preprocess_patents.py
.venv/bin/python src/identification_of_blockchain_patents/extract_blockchain_patents.py
.venv/bin/python src/identification_of_blockchain_patents/extract_blockchain_assignees.py
.venv/bin/python src/identification_of_blockchain_patents/build_bank_patent_dataset.py
.venv/bin/python src/identification_of_blockchain_patents/build_bank_summary_tables.py
```

To write a named run snapshot:

```bash
.venv/bin/python src/run_patent_pipeline.py run 2026-03-16_full_v1
```

To include preprocessing in the same command:

```bash
.venv/bin/python src/run_patent_pipeline.py run 2026-03-16_full_v2 --include-preprocess
```

## Notes

- The blockchain query is a local operationalization of Clarke et al. (2020)
  over USPTO PatentsView tables.
- The preprocessing cohort is defined over granted U.S. patents using grant
  date.
- Filing dates are merged in later so the extracted patent set can also be
  compared in filing-year terms where needed.
