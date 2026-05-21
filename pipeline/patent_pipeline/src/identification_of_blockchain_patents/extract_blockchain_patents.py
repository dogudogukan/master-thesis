"""
Build the blockchain patent set and write the Q1/Q2/Q3 match files.
"""

import os
import sys
import re
import pandas as pd
import pyarrow.parquet as pq

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from config.blockchain_query_config import (
    MAIN_KEYWORDS,
    SECONDARY_KEYWORDS,
    BROAD_CLASSES,
    SPECIFIC_CLASSES,
    Q3_GROUP_A,
    Q3_REQUIRED,
)


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


DATA_DIR = resolve_data_dir()
OUT_ROOT = resolve_out_root()

MATCH_DIR = resolve_stage_dir("01_matches", "matches", "02_matches")
BLOCKCHAIN_PATENTS_DIR = resolve_stage_dir(
    "02_blockchain_patents",
    "blockchain_patents",
    "01_blockchain_patents",
)

Q1_MATCHES = os.path.join(MATCH_DIR, "q1_matches.csv")
Q2_MATCHES = os.path.join(MATCH_DIR, "q2_matches.csv")
Q3_MATCHES = os.path.join(MATCH_DIR, "q3_matches.csv")
EXTRACTED_OUTPUT = os.path.join(BLOCKCHAIN_PATENTS_DIR, "blockchain_patents_extracted.csv")


def ensure_str_id(df, col="patent_id"):
    if col in df.columns:
        df[col] = df[col].astype(str).str.strip()
    return df


def normalize_text(text: str) -> str:
    if text is None:
        return ""
    s = str(text).lower()
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    s = re.sub(r"[^a-z0-9\s-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def keyword_to_regex_base(raw_kw: str) -> str:
    parts = []
    for ch in raw_kw:
        if ch == "-" or ch.isspace():
            # Treat hyphens and spaces as interchangeable so "BLOCK-CHAIN*"
            # also catches spaced forms such as "block chain".
            parts.append(r"[-\s]+")
        else:
            parts.append(re.escape(ch))
    return "".join(parts)


def compile_patterns(keyword_list):
    patterns = []
    for kw in keyword_list:
        raw_kw = kw.lower()
        if raw_kw.endswith("*"):
            base = keyword_to_regex_base(raw_kw[:-1])
            pattern = r"\b" + base + r"\w*"
        else:
            base = keyword_to_regex_base(raw_kw)
            pattern = r"\b" + base + r"\b"
        patterns.append((kw, re.compile(pattern, re.IGNORECASE)))
    return patterns


def load_abstracts_for_ids(target_ids, batch_size=200_000, label="abstracts"):
    print(f"Loading {label} in batches...")
    parquet_path = os.path.join(DATA_DIR, "g_patent_abstract.parquet")
    parquet_file = pq.ParquetFile(parquet_path)

    target_ids = set(map(str, target_ids))
    frames = []
    rows_seen = 0

    for batch_num, batch in enumerate(
        parquet_file.iter_batches(batch_size=batch_size, columns=["patent_id", "patent_abstract"]),
        start=1,
    ):
        df_batch = batch.to_pandas()
        df_batch = ensure_str_id(df_batch)
        rows_seen += len(df_batch)
        df_batch = df_batch[df_batch["patent_id"].isin(target_ids)]
        if not df_batch.empty:
            frames.append(df_batch)
        print(
            f"Scanned {label} batch {batch_num:,}; parquet rows seen: {rows_seen:,}, "
            f"matched abstracts: {sum(len(frame) for frame in frames):,}"
        )

    if not frames:
        return pd.DataFrame(columns=["patent_id", "patent_abstract"])
    return pd.concat(frames, ignore_index=True).drop_duplicates(subset=["patent_id"], keep="first")


def load_patents_with_dates():
    print("Loading patent metadata...")
    df_patent = pd.read_parquet(os.path.join(DATA_DIR, "g_patent.parquet"))
    df_patent = ensure_str_id(df_patent)
    df_patent["grant_date"] = pd.to_datetime(df_patent["patent_date"], errors="coerce")

    print("Loading application data...")
    df_app = pd.read_parquet(os.path.join(DATA_DIR, "g_application.parquet"))
    df_app = ensure_str_id(df_app)
    df_app["filing_date"] = pd.to_datetime(df_app["filing_date"], errors="coerce")
    df_app_min = (
        df_app.dropna(subset=["filing_date"])
        .groupby("patent_id", as_index=False)["filing_date"]
        .min()
    )

    df_patent = df_patent.merge(df_app_min, on="patent_id", how="left")

    missing_filing = int(df_patent["filing_date"].isna().sum())
    print(f"Patents in grant-date cohort: {len(df_patent)}")
    print(f"Patents missing filing_date: {missing_filing}")
    return df_patent


def process_cpc(df_patent):
    print("Loading CPC data...")
    df_cpc = pd.read_parquet(os.path.join(DATA_DIR, "g_cpc_current.parquet"))
    df_cpc = ensure_str_id(df_cpc)
    df_cpc = df_cpc[df_cpc["patent_id"].isin(set(df_patent["patent_id"]))]
    df_cpc["cpc_group"] = df_cpc["cpc_group"].astype(str).str.replace(" ", "")

    q1_ids = set(df_cpc.loc[df_cpc["cpc_class"].isin(BROAD_CLASSES), "patent_id"])
    q2_ids = set(df_cpc.loc[df_cpc["cpc_group"].isin(SPECIFIC_CLASSES), "patent_id"])

    q3_relevant = set(Q3_GROUP_A + [Q3_REQUIRED])
    df_q3 = df_cpc[df_cpc["cpc_group"].isin(q3_relevant)]

    def check_q3(group):
        codes = set(group)
        return (not codes.isdisjoint(Q3_GROUP_A)) and (Q3_REQUIRED in codes)

    q3_candidates = df_q3.groupby("patent_id")["cpc_group"].agg(check_q3)
    q3_ids = set(q3_candidates[q3_candidates].index)

    print(f"Q1 CPC candidates: {len(q1_ids)}")
    print(f"Q2 CPC candidates: {len(q2_ids)}")
    print(f"Q3 CPC matches: {len(q3_ids)}")
    return q1_ids, q2_ids, q3_ids


def perform_text_search(df_patent, q1_cpc_ids, q2_cpc_ids):
    candidate_ids = q1_cpc_ids.union(q2_cpc_ids)
    df_candidate_meta = (
        df_patent[df_patent["patent_id"].isin(candidate_ids)][
            ["patent_id", "patent_title", "filing_date", "grant_date"]
        ]
        .drop_duplicates(subset=["patent_id"], keep="first")
        .copy()
    )
    df_abs = load_abstracts_for_ids(candidate_ids, label="candidate abstracts")
    df_text = df_candidate_meta.merge(df_abs, on="patent_id", how="left")
    print(f"Text candidates after merge: {len(df_text):,}")

    q1_patterns = compile_patterns(MAIN_KEYWORDS)
    q2_patterns = compile_patterns(SECONDARY_KEYWORDS)

    print("Running text search...")
    results = []
    total = len(df_text)
    for i, row in enumerate(df_text.itertuples(index=False), start=1):
        if i % 2000 == 0:
            print(f"Processed {i:,}/{total:,} text items...")
        pid = row.patent_id
        title = "" if pd.isna(row.patent_title) else str(row.patent_title)
        abstract = "" if pd.isna(row.patent_abstract) else str(row.patent_abstract)
        text = normalize_text(
            title + " " + abstract
        )

        is_q1 = False
        q1_kws = []
        if pid in q1_cpc_ids:
            for kw, pat in q1_patterns:
                if pat.search(text):
                    q1_kws.append(kw)
            if q1_kws:
                is_q1 = True

        is_q2 = False
        q2_kws = []
        if pid in q2_cpc_ids:
            for kw, pat in q2_patterns:
                if pat.search(text):
                    q2_kws.append(kw)
            if q2_kws:
                is_q2 = True

        if is_q1 or is_q2:
            results.append(
                {
                    "patent_id": pid,
                    "is_q1": is_q1,
                    "is_q2": is_q2,
                    "q1_keywords": ", ".join(q1_kws),
                    "q2_keywords": ", ".join(q2_kws),
                }
            )

    if not results:
        return pd.DataFrame(
            columns=["patent_id", "is_q1", "is_q2", "q1_keywords", "q2_keywords"]
        )
    return pd.DataFrame(results)


def build_extracted_dataset(df_patent, df_text_matches, q3_ids):
    all_ids = set(df_text_matches["patent_id"]).union(set(map(str, q3_ids)))
    all_ids = sorted(all_ids)

    df_abs = load_abstracts_for_ids(all_ids, label="final abstracts")

    text_idx = df_text_matches.set_index("patent_id") if not df_text_matches.empty else None

    rows = []
    for pid in all_ids:
        is_q1 = False
        is_q2 = False
        q1_keywords = ""
        q2_keywords = ""

        if text_idx is not None and pid in text_idx.index:
            row = text_idx.loc[pid]
            is_q1 = bool(row["is_q1"])
            is_q2 = bool(row["is_q2"])
            q1_keywords = row["q1_keywords"]
            q2_keywords = row["q2_keywords"]

        is_q3 = pid in q3_ids
        sources = []
        if is_q1:
            sources.append("Q1")
        if is_q2:
            sources.append("Q2")
        if is_q3:
            sources.append("Q3")

        rows.append(
            {
                "patent_id": pid,
                "match_source": ", ".join(sources),
                "is_q1": is_q1,
                "is_q2": is_q2,
                "is_q3": is_q3,
                "q1_keywords": q1_keywords,
                "q2_keywords": q2_keywords,
            }
        )

    df_extracted = pd.DataFrame(rows)
    if df_extracted.empty:
        return df_extracted

    df_extracted = ensure_str_id(df_extracted)
    df_extracted = df_extracted.merge(
        df_patent[["patent_id", "patent_title", "filing_date", "grant_date"]],
        on="patent_id",
        how="left",
    ).merge(df_abs, on="patent_id", how="left")

    return df_extracted


def main():
    os.makedirs(MATCH_DIR, exist_ok=True)
    os.makedirs(BLOCKCHAIN_PATENTS_DIR, exist_ok=True)

    print(">>> Q1/Q2/Q3 EXTRACTION PIPELINE <<<")
    print(f"Data directory: {DATA_DIR}")
    print(f"Output directory: {OUT_ROOT}")

    df_patent = load_patents_with_dates()
    q1_cpc_ids, q2_cpc_ids, q3_ids = process_cpc(df_patent)

    df_text_matches = perform_text_search(df_patent, q1_cpc_ids, q2_cpc_ids)
    df_text_matches = ensure_str_id(df_text_matches)

    df_extracted = build_extracted_dataset(df_patent, df_text_matches, q3_ids)
    df_q1 = df_extracted[df_extracted["is_q1"]].copy()
    df_q2 = df_extracted[df_extracted["is_q2"]].copy()
    df_q3 = df_extracted[df_extracted["is_q3"]].copy()

    df_q1.to_csv(Q1_MATCHES, index=False)
    df_q2.to_csv(Q2_MATCHES, index=False)
    df_q3.to_csv(Q3_MATCHES, index=False)
    print(f"Wrote: {Q1_MATCHES} ({len(df_q1)})")
    print(f"Wrote: {Q2_MATCHES} ({len(df_q2)})")
    print(f"Wrote: {Q3_MATCHES} ({len(df_q3)})")

    df_extracted.to_csv(EXTRACTED_OUTPUT, index=False)
    print(f"Wrote: {EXTRACTED_OUTPUT} ({len(df_extracted)})")


if __name__ == "__main__":
    main()
