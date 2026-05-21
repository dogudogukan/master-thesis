"""
Path settings for the patent pipeline.

I keep the raw and processed file locations here so preprocessing reads from
one place. The project now uses only `data/raw` and `data/processed`.
"""

from pathlib import Path


# Base project and data directories.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"


# All files in this project come from PatentsView.
RAW_PATENT_DIR = RAW_DATA_DIR
PROCESSED_PATENT_DIR = PROCESSED_DATA_DIR


# Expected raw PatentsView input files.
RAW_FILES = {
    "patent": RAW_DATA_DIR / "g_patent.tsv.zip",
    "application": RAW_DATA_DIR / "g_application.tsv.zip",
    "assignee": RAW_DATA_DIR / "g_assignee_disambiguated.tsv.zip",
    "cpc": RAW_DATA_DIR / "g_cpc_current.tsv.zip",
    "citation": RAW_DATA_DIR / "g_us_patent_citation.tsv.zip",
    "abstract": RAW_DATA_DIR / "g_patent_abstract.tsv.zip",
    "inventor": RAW_DATA_DIR / "g_inventor_disambiguated.tsv.zip",
    "pct": RAW_DATA_DIR / "g_pct_data.tsv.zip",
    "rel_doc": RAW_DATA_DIR / "g_us_rel_doc.tsv.zip",
}

# Claims come as one zip file per year.
CLAIMS_YEARS = range(2008, 2026)
RAW_CLAIMS_FILES = {
    year: RAW_DATA_DIR / f"g_claims_{year}.tsv.zip"
    for year in CLAIMS_YEARS
}


# Processed parquet files written by preprocessing.
PROCESSED_FILES = {
    "patent": PROCESSED_DATA_DIR / "g_patent.parquet",
    "application": PROCESSED_DATA_DIR / "g_application.parquet",
    "assignee": PROCESSED_DATA_DIR / "g_assignee_disambiguated.parquet",
    "cpc": PROCESSED_DATA_DIR / "g_cpc_current.parquet",
    "citation": PROCESSED_DATA_DIR / "g_us_patent_citation.parquet",
    "abstract": PROCESSED_DATA_DIR / "g_patent_abstract.parquet",
    "claims": PROCESSED_DATA_DIR / "g_claims.parquet",
    "inventor": PROCESSED_DATA_DIR / "g_inventor_disambiguated.parquet",
    "pct": PROCESSED_DATA_DIR / "g_pct_data.parquet",
    "rel_doc": PROCESSED_DATA_DIR / "g_us_rel_doc.parquet",
}
