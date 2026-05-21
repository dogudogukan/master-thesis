"""
List the assignees attached to the extracted blockchain patent set.

Inputs:
- results/02_blockchain_patents/blockchain_patents_extracted.csv
- data/processed/g_assignee_disambiguated.parquet

Output:
- results/03_final/unique_assignees.csv
"""

import os
import sys

import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)


def resolve_out_root() -> str:
    env_out_root = os.getenv("PATENT_PIPELINE_OUT_ROOT")
    if env_out_root:
        return os.path.abspath(env_out_root)
    return os.path.join(PROJECT_ROOT, "results")


def resolve_stage_dir(*names: str) -> str:
    return os.path.join(OUT_ROOT, names[0])


def resolve_data_dir() -> str:
    env_data_dir = os.getenv("PATENT_DATA_DIR")
    if env_data_dir:
        return os.path.abspath(env_data_dir)
    return os.path.join(PROJECT_ROOT, "data", "processed")


OUT_ROOT = resolve_out_root()
DATA_DIR = resolve_data_dir()

BLOCKCHAIN_PATENTS_DIR = resolve_stage_dir(
    "02_blockchain_patents",
    "blockchain_patents",
    "01_blockchain_patents",
)
FINAL_DIR = resolve_stage_dir("03_final", "final")

EXTRACTED_PATENTS_CSV = os.path.join(BLOCKCHAIN_PATENTS_DIR, "blockchain_patents_extracted.csv")
ASSIGNEE_PARQUET = os.path.join(DATA_DIR, "g_assignee_disambiguated.parquet")
OUT_UNIQUE_ASSIGNEES = os.path.join(FINAL_DIR, "unique_assignees.csv")


def main() -> None:
    if not os.path.exists(EXTRACTED_PATENTS_CSV):
        raise FileNotFoundError(f"Missing input: {EXTRACTED_PATENTS_CSV}")
    if not os.path.exists(ASSIGNEE_PARQUET):
        raise FileNotFoundError(f"Missing input: {ASSIGNEE_PARQUET}")

    print(f"Loading extracted patents: {EXTRACTED_PATENTS_CSV}")
    df_patents = pd.read_csv(EXTRACTED_PATENTS_CSV, usecols=["patent_id"])
    patent_ids = set(df_patents["patent_id"].astype(str).str.strip())

    print(f"Loading assignee mapping: {ASSIGNEE_PARQUET}")
    df_assg = pd.read_parquet(
        ASSIGNEE_PARQUET,
        columns=["patent_id", "assignee_id", "disambig_assignee_organization"],
    )
    df_assg["patent_id"] = df_assg["patent_id"].astype(str).str.strip()
    df_assg = df_assg[df_assg["patent_id"].isin(patent_ids)].copy()

    df_unique = (
        df_assg.groupby(
            ["assignee_id", "disambig_assignee_organization"],
            dropna=False,
        )["patent_id"]
        .nunique()
        .reset_index(name="blockchain_patent_count")
        .sort_values(
            ["blockchain_patent_count", "disambig_assignee_organization"],
            ascending=[False, True],
        )
    )

    os.makedirs(os.path.dirname(OUT_UNIQUE_ASSIGNEES), exist_ok=True)
    df_unique.to_csv(OUT_UNIQUE_ASSIGNEES, index=False)

    print(f"Wrote: {OUT_UNIQUE_ASSIGNEES} ({len(df_unique)} rows)")
    print(f"Unique patents in extracted set: {len(patent_ids)}")


if __name__ == "__main__":
    main()
