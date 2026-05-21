"""
Build the bank-level summary tables from patents.csv.

Inputs:
- results/03_final/patents.csv

Outputs:
- results/03_final/ranking.csv
- results/03_final/counts.csv
- results/03_final/counts_over_time.csv
"""

import os
import sys

import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)


US_TOP50_BANKS = [
    (1, "JPMorgan Chase"),
    (2, "Bank of America"),
    (3, "Citigroup"),
    (4, "Wells Fargo"),
    (5, "Goldman Sachs"),
    (6, "Morgan Stanley"),
    (7, "U.S. Bancorp"),
    (8, "Capital One"),
    (9, "PNC"),
    (10, "Truist"),
    (11, "TD Group US Holdings"),
    (12, "Charles Schwab"),
    (13, "BNY Mellon"),
    (14, "State Street"),
    (15, "American Express"),
    (16, "Fifth Third"),
    (17, "BMO"),
    (18, "Huntington Bancshares"),
    (19, "First Citizens BancShares"),
    (20, "HSBC North America Holdings"),
    (21, "USAA"),
    (22, "Citizens Financial Group"),
    (23, "Barclays US"),
    (24, "M&T Bank"),
    (25, "UBS Americas Holdings"),
    (26, "RBC US Group Holdings"),
    (27, "Ally Financial"),
    (28, "KeyCorp"),
    (29, "Northern Trust"),
    (30, "Santander Holdings USA"),
    (31, "Regions Financial"),
    (32, "Synchrony Financial"),
    (33, "Pinnacle Financial Partners"),
    (34, "Flagstar Bank"),
    (35, "Western Alliance Bancorp"),
    (36, "Zions Bancorp"),
    (37, "Raymond James Financial"),
    (38, "First Horizon"),
    (39, "Webster Financial"),
    (40, "East West Bancorp"),
    (41, "CIBC Bancorp USA"),
    (42, "Popular"),
    (43, "UMB Financial"),
    (44, "Old National Bancorp"),
    (45, "Wintrust Financial"),
    (46, "Columbia Banking System"),
    (47, "SouthState Bank"),
    (48, "Valley National Bancorp"),
    (49, "Cullen/Frost Bankers"),
    (50, "BOK Financial"),
]


def resolve_out_root() -> str:
    env_out_root = os.getenv("PATENT_PIPELINE_OUT_ROOT")
    if env_out_root:
        return os.path.abspath(env_out_root)
    return os.path.join(PROJECT_ROOT, "results")


def resolve_stage_dir(*names: str) -> str:
    return os.path.join(OUT_ROOT, names[0])


def join_unique(values: pd.Series) -> str:
    cleaned = sorted({str(v).strip() for v in values.dropna() if str(v).strip()})
    return " | ".join(cleaned)


def split_joined(value: str) -> list[str]:
    if pd.isna(value):
        return []
    return [part.strip() for part in str(value).split("|") if part.strip()]


OUT_ROOT = resolve_out_root()
FINAL_DIR = resolve_stage_dir("03_final", "final")

PATENTS_CSV = os.path.join(FINAL_DIR, "patents.csv")
RANKING_CSV = os.path.join(FINAL_DIR, "ranking.csv")
COUNTS_CSV = os.path.join(FINAL_DIR, "counts.csv")
COUNTS_OVER_TIME_CSV = os.path.join(FINAL_DIR, "counts_over_time.csv")


def load_patents() -> pd.DataFrame:
    if not os.path.exists(PATENTS_CSV):
        raise FileNotFoundError(f"Missing input: {PATENTS_CSV}")

    df = pd.read_csv(
        PATENTS_CSV,
        dtype={
            "patent_id": "string",
            "canonical_bank_name": "string",
            "parent_bank_group": "string",
            "us_top50_bank_name": "string",
            "assignee_ids": "string",
        },
    )
    df["patent_id"] = df["patent_id"].astype("string").str.strip()
    df["canonical_bank_name"] = df["canonical_bank_name"].astype("string").str.strip()
    df["parent_bank_group"] = df["parent_bank_group"].astype("string").str.strip()
    df["us_top50_bank_name"] = df["us_top50_bank_name"].astype("string").str.strip()
    df["assignee_ids"] = df["assignee_ids"].astype("string").str.strip()
    df["grant_date"] = pd.to_datetime(df["grant_date"], errors="coerce")
    df["us_top50_rank"] = pd.to_numeric(df["us_top50_rank"], errors="coerce").astype("Int64")
    df["is_us_top50_candidate"] = pd.to_numeric(
        df["is_us_top50_candidate"], errors="coerce"
    ).fillna(0).astype(int)
    df["assignee_count"] = pd.to_numeric(df["assignee_count"], errors="coerce").fillna(0).astype(int)
    return df


def build_ranking(df: pd.DataFrame) -> pd.DataFrame:
    exploded_ids = (
        df[["canonical_bank_name", "assignee_ids"]]
        .dropna(subset=["canonical_bank_name"])
        .assign(assignee_id=lambda x: x["assignee_ids"].map(split_joined))
        .explode("assignee_id")
    )
    exploded_ids["assignee_id"] = exploded_ids["assignee_id"].astype("string").str.strip()
    exploded_ids = exploded_ids[exploded_ids["assignee_id"].notna() & (exploded_ids["assignee_id"] != "")]

    distinct_assignee_counts = (
        exploded_ids.groupby("canonical_bank_name")["assignee_id"].nunique()
        if not exploded_ids.empty
        else pd.Series(dtype="int64")
    )

    ranking = (
        df.groupby("canonical_bank_name", as_index=False, dropna=False)
        .agg(
            parent_bank_group=("parent_bank_group", join_unique),
            is_us_top50_candidate=("is_us_top50_candidate", "max"),
            assignee_link_count=("assignee_count", "sum"),
            unique_patent_count=("patent_id", "nunique"),
        )
        .sort_values(
            ["unique_patent_count", "canonical_bank_name"],
            ascending=[False, True],
            na_position="last",
        )
        .reset_index(drop=True)
    )

    ranking["assignee_count"] = (
        ranking["canonical_bank_name"].map(distinct_assignee_counts).fillna(0).astype(int)
    )
    ranking.insert(0, "rank", range(1, len(ranking) + 1))

    return ranking[
        [
            "rank",
            "canonical_bank_name",
            "parent_bank_group",
            "is_us_top50_candidate",
            "assignee_count",
            "assignee_link_count",
            "unique_patent_count",
        ]
    ]


def build_counts(df: pd.DataFrame) -> pd.DataFrame:
    scaffold = pd.DataFrame(US_TOP50_BANKS, columns=["us_top50_rank", "us_top50_bank_name"])

    top50_counts = (
        df[df["is_us_top50_candidate"] == 1]
        .groupby(["us_top50_rank", "us_top50_bank_name"], as_index=False, dropna=False)
        .agg(
            mapped_canonical_bank=("canonical_bank_name", join_unique),
            unique_patent_count=("patent_id", "nunique"),
            parent_bank_group=("parent_bank_group", join_unique),
        )
    )

    counts = scaffold.merge(top50_counts, on=["us_top50_rank", "us_top50_bank_name"], how="left")
    counts["mapped_canonical_bank"] = counts["mapped_canonical_bank"].fillna("")
    counts["parent_bank_group"] = counts["parent_bank_group"].fillna("")
    counts["unique_patent_count"] = counts["unique_patent_count"].fillna(0).astype(int)
    return counts


def build_counts_over_time(df: pd.DataFrame) -> pd.DataFrame:
    counts_over_time = df.copy()
    counts_over_time["grant_year"] = counts_over_time["grant_date"].dt.year.astype("Int64")
    counts_over_time = counts_over_time.dropna(subset=["grant_year"])

    counts_over_time = (
        counts_over_time.groupby(["canonical_bank_name", "grant_year"], as_index=False, dropna=False)
        .agg(unique_patent_count=("patent_id", "nunique"))
        .sort_values(["canonical_bank_name", "grant_year"], ascending=[True, True], na_position="last")
    )

    counts_over_time["grant_year"] = counts_over_time["grant_year"].astype(int)
    return counts_over_time


def main() -> None:
    df = load_patents()
    ranking = build_ranking(df)
    counts = build_counts(df)
    counts_over_time = build_counts_over_time(df)

    os.makedirs(FINAL_DIR, exist_ok=True)
    ranking.to_csv(RANKING_CSV, index=False)
    counts.to_csv(COUNTS_CSV, index=False)
    counts_over_time.to_csv(COUNTS_OVER_TIME_CSV, index=False)

    print(f"Wrote: {RANKING_CSV} ({len(ranking)} rows)")
    print(f"Wrote: {COUNTS_CSV} ({len(counts)} rows)")
    print(f"Wrote: {COUNTS_OVER_TIME_CSV} ({len(counts_over_time)} rows)")


if __name__ == "__main__":
    main()
