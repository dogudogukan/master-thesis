"""
Build the final patent-level bank dataset from the extracted blockchain patents.

Inputs:
- results/02_blockchain_patents/blockchain_patents_extracted.csv
- data/processed/g_assignee_disambiguated.parquet
- mapping/unique_assignees_bank_mapping.csv

Output:
- results/03_final/patents.csv
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


def resolve_bank_mapping_csv() -> str:
    env_mapping_csv = os.getenv("BANK_ASSIGNEE_MAPPING_CSV")
    if env_mapping_csv:
        return os.path.abspath(env_mapping_csv)
    return os.path.join(PROJECT_ROOT, "mapping", "unique_assignees_bank_mapping.csv")


def ensure_str_col(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if col in df.columns:
        df[col] = df[col].astype("string").str.strip()
    return df


def join_unique(values: pd.Series) -> str:
    cleaned = sorted({str(v).strip() for v in values.dropna() if str(v).strip()})
    return " | ".join(cleaned)


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
BANK_MAPPING_CSV = resolve_bank_mapping_csv()
OUT_PATENTS_CSV = os.path.join(FINAL_DIR, "patents.csv")


def main() -> None:
    for path in (EXTRACTED_PATENTS_CSV, ASSIGNEE_PARQUET, BANK_MAPPING_CSV):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing input: {path}")

    print(f"Loading extracted patents: {EXTRACTED_PATENTS_CSV}")
    df_patents = pd.read_csv(
        EXTRACTED_PATENTS_CSV,
        usecols=[
            "patent_id",
            "match_source",
            "is_q1",
            "is_q2",
            "is_q3",
            "q1_keywords",
            "q2_keywords",
            "patent_title",
            "filing_date",
            "grant_date",
        ],
        dtype={"patent_id": "string"},
    )
    df_patents = ensure_str_col(df_patents, "patent_id")
    patent_ids = set(df_patents["patent_id"].dropna())

    print(f"Loading assignee links: {ASSIGNEE_PARQUET}")
    df_assignees = pd.read_parquet(
        ASSIGNEE_PARQUET,
        columns=["patent_id", "assignee_id", "disambig_assignee_organization"],
    )
    df_assignees = ensure_str_col(df_assignees, "patent_id")
    df_assignees = ensure_str_col(df_assignees, "assignee_id")
    df_assignees = df_assignees[df_assignees["patent_id"].isin(patent_ids)].copy()

    print(f"Loading bank assignee mapping: {BANK_MAPPING_CSV}")
    df_bank_map = pd.read_csv(
        BANK_MAPPING_CSV,
        usecols=[
            "assignee_id",
            "disambig_assignee_organization",
            "is_bank",
            "canonical_bank_name",
            "parent_bank_group",
            "is_us_top50_candidate",
            "us_top50_rank",
            "us_top50_bank_name",
            "match_type",
            "confidence",
        ],
        dtype={"assignee_id": "string"},
    )
    df_bank_map = ensure_str_col(df_bank_map, "assignee_id")
    df_bank_map = df_bank_map[df_bank_map["is_bank"] == 1].copy()
    df_bank_map = df_bank_map.drop_duplicates(subset=["assignee_id"])

    df_bank_links = df_assignees.merge(
        df_bank_map,
        on="assignee_id",
        how="inner",
        suffixes=("", "_mapped"),
    )
    df_bank_links["assignee_organization"] = df_bank_links["disambig_assignee_organization"].combine_first(
        df_bank_links["disambig_assignee_organization_mapped"]
    )

    df_bank_patents = df_patents.merge(df_bank_links, on="patent_id", how="inner")

    grouped = (
        df_bank_patents.groupby(
            [
                "canonical_bank_name",
                "parent_bank_group",
                "is_us_top50_candidate",
                "us_top50_rank",
                "us_top50_bank_name",
                "patent_id",
                "match_source",
                "is_q1",
                "is_q2",
                "is_q3",
                "q1_keywords",
                "q2_keywords",
                "patent_title",
                "filing_date",
                "grant_date",
            ],
            dropna=False,
            as_index=False,
        ).agg(
            assignee_count=("assignee_id", "nunique"),
            assignee_ids=("assignee_id", join_unique),
            assignee_organizations=("assignee_organization", join_unique),
            match_types=("match_type", join_unique),
            confidences=("confidence", join_unique),
        )
    )

    grouped["is_us_top50_candidate"] = grouped["is_us_top50_candidate"].fillna(0).astype(int)
    grouped["us_top50_rank"] = pd.to_numeric(grouped["us_top50_rank"], errors="coerce").astype("Int64")
    grouped = grouped[grouped["is_us_top50_candidate"] == 1].copy()

    grouped = grouped[
        [
            "patent_id",
            "canonical_bank_name",
            "parent_bank_group",
            "is_us_top50_candidate",
            "us_top50_rank",
            "us_top50_bank_name",
            "assignee_count",
            "assignee_ids",
            "assignee_organizations",
            "match_types",
            "confidences",
            "match_source",
            "is_q1",
            "is_q2",
            "is_q3",
            "q1_keywords",
            "q2_keywords",
            "patent_title",
            "filing_date",
            "grant_date",
        ]
    ].sort_values(
        [
            "is_us_top50_candidate",
            "us_top50_rank",
            "canonical_bank_name",
            "grant_date",
            "filing_date",
            "patent_id",
        ],
        ascending=[False, True, True, True, True, True],
        na_position="last",
    )

    os.makedirs(FINAL_DIR, exist_ok=True)
    grouped.to_csv(OUT_PATENTS_CSV, index=False)

    print(f"Wrote: {OUT_PATENTS_CSV} ({len(grouped)} rows)")
    print(f"Unique top-50 banks: {grouped['canonical_bank_name'].nunique()}")
    print(f"Unique patents: {grouped['patent_id'].nunique()}")


if __name__ == "__main__":
    main()
