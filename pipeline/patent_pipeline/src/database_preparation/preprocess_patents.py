"""
USPTO PatentsView preprocessing.

This script converts raw PatentsView TSV.ZIP files into filtered Parquet files.
The preprocessing step keeps selected columns, applies the grant-date cohort
filter, and writes the outputs in chunks so the full raw files do not need to
fit in memory at once.
"""

import json
import logging
import os
import sys
import warnings
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Allow `import config...` to work regardless of the current working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from config.column_config import COLUMNS, DTYPE_MAPPINGS
from config.path_config import PROCESSED_DATA_DIR, PROCESSED_FILES, RAW_CLAIMS_FILES, RAW_FILES
from config.processing_config import CHUNK_SIZE, DATE_RANGE, NA_VALUES, PARQUET_COMPRESSION

warnings.filterwarnings("ignore", category=pd.errors.DtypeWarning)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


PREPROCESS_OVERWRITE = os.getenv("PREPROCESS_OVERWRITE", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
}
COHORT_DATE_FIELD = "patent_date"  # grant date (g_patent.patent_date)
METADATA_PATH = PROCESSED_DATA_DIR / "_preprocess_metadata.json"


def _expected_metadata() -> dict:
    return {
        "cohort_date_field": COHORT_DATE_FIELD,
        "date_range": {"start": DATE_RANGE["start"], "end": DATE_RANGE["end"]},
    }


def _load_metadata() -> Optional[dict]:
    if not METADATA_PATH.exists():
        return None
    try:
        return json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Could not read metadata file {METADATA_PATH.name}: {e}")
        return None


def _write_metadata() -> None:
    meta = _expected_metadata()
    meta["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    METADATA_PATH.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")


def _assert_metadata_or_raise() -> None:
    """
    Prevent silent reuse of Parquet files created with a different cohort definition.

    If any processed parquet exists but metadata is missing or mismatched, require
    PREPROCESS_OVERWRITE=1 (or manual cleanup) to proceed.
    """
    existing_parquets = list(PROCESSED_DATA_DIR.glob("g_*.parquet"))
    meta = _load_metadata()
    expected = _expected_metadata()

    if meta is None:
        if existing_parquets and not PREPROCESS_OVERWRITE:
            raise RuntimeError(
                "Existing Parquet files found but preprocessing metadata is missing. "
                "To switch the cohort definition safely, delete files under "
                f"{PROCESSED_DATA_DIR} or re-run with PREPROCESS_OVERWRITE=1."
            )
        return

    if (
        meta.get("cohort_date_field") != expected["cohort_date_field"]
        or meta.get("date_range") != expected["date_range"]
    ):
        if not PREPROCESS_OVERWRITE:
            raise RuntimeError(
                "Existing Parquet files were generated with a different cohort definition "
                f"(found {meta.get('cohort_date_field')} / {meta.get('date_range')}). "
                "Delete processed Parquet files or re-run with PREPROCESS_OVERWRITE=1."
            )


def _build_arrow_schema(usecols: list, dtype: dict) -> pa.Schema:
    arrow_type_map = {
        "string": pa.string(),
        "Int64": pa.int64(),
    }
    return pa.schema(
        [(col, arrow_type_map.get(dtype.get(col, "string"), pa.string())) for col in usecols]
    )


def _write_empty_parquet(output_path: Path, usecols: list, dtype: dict) -> None:
    schema = _build_arrow_schema(usecols, dtype)
    pq.write_table(
        pa.Table.from_arrays(
            [pa.array([], type=field.type) for field in schema],
            schema=schema,
        ),
        output_path,
        compression=PARQUET_COMPRESSION,
    )


def _parquet_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    return pq.ParquetFile(path).metadata.num_rows


def process_file_chunked(
    zip_path: Path,
    output_path: Path,
    usecols: list,
    dtype: dict,
    filter_patents: Optional[Set[str]] = None,
    filter_column: str = "patent_id",
    overwrite: bool = False,
) -> int:
    """Process a TSV.ZIP file in chunks and write to Parquet."""
    if output_path.exists() and not overwrite:
        logger.info(f"  ✓ Skipping (exists): {output_path.name}")
        return 0
    if overwrite and output_path.exists():
        output_path.unlink()

    logger.info(f"Processing: {zip_path.name}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_rows = 0
    writer = None

    try:
        with zipfile.ZipFile(zip_path) as z:
            tsv_name = [n for n in z.namelist() if n.endswith(".tsv")][0]

            with z.open(tsv_name) as f:
                chunks = pd.read_csv(
                    f,
                    sep="\t",
                    usecols=usecols,
                    dtype=dtype,
                    chunksize=CHUNK_SIZE,
                    na_values=NA_VALUES,
                    keep_default_na=True,
                    low_memory=False,
                )

                for i, chunk in enumerate(chunks):
                    if filter_patents is not None:
                        chunk = chunk[chunk[filter_column].isin(filter_patents)]

                    if chunk.empty:
                        continue

                    for col in chunk.columns:
                        if chunk[col].dtype == "string" or chunk[col].dtype == object:
                            chunk[col] = chunk[col].fillna("")

                    table = pa.Table.from_pandas(chunk, preserve_index=False)

                    if writer is None:
                        writer = pq.ParquetWriter(
                            output_path,
                            table.schema,
                            compression=PARQUET_COMPRESSION,
                        )

                    writer.write_table(table)
                    total_rows += len(chunk)

                    if (i + 1) % 10 == 0:
                        logger.info(f"  Processed {total_rows:,} rows...")

    finally:
        if writer is not None:
            writer.close()

    # Keep the output contract stable even when no rows survive the filter.
    if writer is None:
        _write_empty_parquet(output_path, usecols, dtype)

    logger.info(f"  ✓ Completed: {total_rows:,} rows → {output_path.name}")
    return total_rows


def process_patent_file() -> Set[str]:
    """Process g_patent.tsv.zip with grant-date filtering and return cohort patent IDs."""
    if PROCESSED_FILES["patent"].exists() and not PREPROCESS_OVERWRITE:
        logger.info("Loading cohort patent IDs from existing patent parquet...")
        table = pq.read_table(PROCESSED_FILES["patent"], columns=["patent_id"])
        valid_patents = set(table.column("patent_id").to_pylist())
        logger.info(f"Loaded {len(valid_patents):,} cohort patents")
        return valid_patents

    logger.info("=" * 60)
    logger.info("Processing PATENT file with grant-date filtering...")
    logger.info("=" * 60)

    zip_path = RAW_FILES["patent"]
    if not zip_path.exists():
        raise FileNotFoundError(f"Required raw file not found: {zip_path}")
    output_path = PROCESSED_FILES["patent"]
    usecols = COLUMNS["patent"]
    dtype = DTYPE_MAPPINGS["patent"]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if PREPROCESS_OVERWRITE and output_path.exists():
        output_path.unlink()

    total_rows = 0
    writer = None
    valid_patents: Set[str] = set()

    try:
        with zipfile.ZipFile(zip_path) as z:
            tsv_name = [n for n in z.namelist() if n.endswith(".tsv")][0]

            with z.open(tsv_name) as f:
                chunks = pd.read_csv(
                    f,
                    sep="\t",
                    usecols=usecols,
                    dtype=dtype,
                    chunksize=CHUNK_SIZE,
                    na_values=NA_VALUES,
                    keep_default_na=True,
                    low_memory=False,
                )

                for i, chunk in enumerate(chunks):
                    chunk["patent_date"] = pd.to_datetime(
                        chunk["patent_date"],
                        format="%Y-%m-%d",
                        errors="coerce",
                    )

                    mask = (
                        (chunk["patent_date"] >= DATE_RANGE["start"])
                        & (chunk["patent_date"] <= DATE_RANGE["end"])
                    )
                    chunk = chunk[mask]

                    if chunk.empty:
                        continue

                    patent_ids = chunk["patent_id"].dropna().astype(str).str.strip()
                    valid_patents.update(pid for pid in patent_ids if pid)
                    chunk["patent_date"] = chunk["patent_date"].dt.strftime("%Y-%m-%d")

                    for col in chunk.columns:
                        if chunk[col].dtype == "string" or chunk[col].dtype == object:
                            chunk[col] = chunk[col].fillna("")

                    table = pa.Table.from_pandas(chunk, preserve_index=False)

                    if writer is None:
                        writer = pq.ParquetWriter(
                            output_path,
                            table.schema,
                            compression=PARQUET_COMPRESSION,
                        )

                    writer.write_table(table)
                    total_rows += len(chunk)

                    if (i + 1) % 5 == 0:
                        logger.info(
                            f"  Processed {total_rows:,} rows, {len(valid_patents):,} cohort patents..."
                        )

    finally:
        if writer is not None:
            writer.close()

    # Keep the output contract stable even when no cohort rows exist.
    if writer is None:
        _write_empty_parquet(output_path, usecols, dtype)

    logger.info(f"  ✓ Patent file completed: {total_rows:,} rows")
    logger.info(
        f"  ✓ Cohort patents (grant_date {DATE_RANGE['start']}..{DATE_RANGE['end']}): {len(valid_patents):,}"
    )

    return valid_patents


def process_application_file(valid_patents: Set[str]) -> int:
    """Process g_application.tsv.zip filtered by the grant-date cohort and keep filing_date."""
    if PROCESSED_FILES["application"].exists() and not PREPROCESS_OVERWRITE:
        logger.info("  ✓ Skipping application (exists): g_application.parquet")
        return 0

    logger.info("=" * 60)
    logger.info("Processing APPLICATION file filtered by grant-date cohort...")
    logger.info("=" * 60)

    zip_path = RAW_FILES["application"]
    if not zip_path.exists():
        raise FileNotFoundError(f"Required raw file not found: {zip_path}")
    output_path = PROCESSED_FILES["application"]
    usecols = COLUMNS["application"]
    dtype = DTYPE_MAPPINGS["application"]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if PREPROCESS_OVERWRITE and output_path.exists():
        output_path.unlink()

    total_rows = 0
    writer = None

    try:
        with zipfile.ZipFile(zip_path) as z:
            tsv_name = [n for n in z.namelist() if n.endswith(".tsv")][0]

            with z.open(tsv_name) as f:
                chunks = pd.read_csv(
                    f,
                    sep="\t",
                    usecols=usecols,
                    dtype=dtype,
                    chunksize=CHUNK_SIZE,
                    na_values=NA_VALUES,
                    keep_default_na=True,
                    low_memory=False,
                )

                for i, chunk in enumerate(chunks):
                    chunk = chunk[chunk["patent_id"].isin(valid_patents)]
                    if chunk.empty:
                        continue

                    chunk["filing_date"] = pd.to_datetime(
                        chunk["filing_date"],
                        format="%Y-%m-%d",
                        errors="coerce",
                    )
                    chunk["filing_date"] = chunk["filing_date"].dt.strftime("%Y-%m-%d")

                    for col in chunk.columns:
                        if chunk[col].dtype == "string" or chunk[col].dtype == object:
                            chunk[col] = chunk[col].fillna("")

                    table = pa.Table.from_pandas(chunk, preserve_index=False)

                    if writer is None:
                        writer = pq.ParquetWriter(
                            output_path,
                            table.schema,
                            compression=PARQUET_COMPRESSION,
                        )

                    writer.write_table(table)
                    total_rows += len(chunk)

                    if (i + 1) % 10 == 0:
                        logger.info(f"  Processed {total_rows:,} rows...")

    finally:
        if writer is not None:
            writer.close()

    # Keep output contract stable for downstream even when no cohort rows exist.
    if writer is None:
        _write_empty_parquet(output_path, usecols, dtype)

    logger.info(f"  ✓ Application file completed: {total_rows:,} rows → {output_path.name}")
    return total_rows


def process_claims_files(valid_patents: Set[str]) -> int:
    """Process yearly claims files (2008-2025) into a single Parquet."""
    if PROCESSED_FILES["claims"].exists() and not PREPROCESS_OVERWRITE:
        logger.info("  ✓ Skipping claims (exists): g_claims.parquet")
        return 0

    logger.info("=" * 60)
    logger.info("Processing CLAIMS files (2008-2025)...")
    logger.info("=" * 60)

    output_path = PROCESSED_FILES["claims"]
    usecols = COLUMNS["claims"]
    dtype = DTYPE_MAPPINGS["claims"]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if PREPROCESS_OVERWRITE and output_path.exists():
        output_path.unlink()

    total_rows = 0
    writer = None

    try:
        for year, zip_path in sorted(RAW_CLAIMS_FILES.items()):
            if not zip_path.exists():
                logger.warning(f"  Claims file not found: {zip_path.name}")
                continue

            logger.info(f"  Processing claims {year}...")
            year_rows = 0

            with zipfile.ZipFile(zip_path) as z:
                tsv_name = [n for n in z.namelist() if n.endswith(".tsv")][0]

                with z.open(tsv_name) as f:
                    chunks = pd.read_csv(
                        f,
                        sep="\t",
                        usecols=usecols,
                        dtype=dtype,
                        chunksize=CHUNK_SIZE,
                        na_values=NA_VALUES,
                        keep_default_na=True,
                        low_memory=False,
                    )

                    for chunk in chunks:
                        chunk = chunk[chunk["patent_id"].isin(valid_patents)]

                        if chunk.empty:
                            continue

                        for col in chunk.columns:
                            if chunk[col].dtype == "string" or chunk[col].dtype == object:
                                chunk[col] = chunk[col].fillna("")

                        table = pa.Table.from_pandas(chunk, preserve_index=False)

                        if writer is None:
                            writer = pq.ParquetWriter(
                                output_path,
                                table.schema,
                                compression=PARQUET_COMPRESSION,
                            )

                        writer.write_table(table)
                        year_rows += len(chunk)

            total_rows += year_rows
            logger.info(f"    ✓ {year}: {year_rows:,} claims")

    finally:
        if writer is None:
            logger.warning("  No claims data written!")
            _write_empty_parquet(output_path, usecols, dtype)
        else:
            writer.close()

    logger.info(f"  ✓ Claims files completed: {total_rows:,} total rows")
    return total_rows


def process_other_files(valid_patents: Set[str]) -> dict:
    """Process remaining files filtered by valid patent IDs."""
    logger.info("=" * 60)
    logger.info("Processing other files...")
    logger.info("=" * 60)

    files_to_process = [
        "assignee",
        "cpc",
        "citation",
        "abstract",
        "inventor",
        "pct",
        "rel_doc",
    ]
    results = {}

    for file_key in files_to_process:
        zip_path = RAW_FILES[file_key]
        output_path = PROCESSED_FILES[file_key]
        usecols = COLUMNS[file_key]
        dtype = DTYPE_MAPPINGS[file_key]

        if not zip_path.exists():
            logger.warning(f"  File not found: {zip_path.name}")
            if PREPROCESS_OVERWRITE and output_path.exists():
                output_path.unlink()
                logger.warning(f"  Removed stale output due to missing raw file: {output_path.name}")
            results[file_key] = 0
            continue

        try:
            rows = process_file_chunked(
                zip_path=zip_path,
                output_path=output_path,
                usecols=usecols,
                dtype=dtype,
                filter_patents=valid_patents,
                filter_column="patent_id",
                overwrite=PREPROCESS_OVERWRITE,
            )
            results[file_key] = rows
        except Exception as e:
            logger.error(f"  Error processing {file_key}: {e}")
            results[file_key] = 0

    return results


def run_preprocessing_pipeline():
    """Run the complete preprocessing pipeline."""
    logger.info("=" * 60)
    logger.info("USPTO PATENTSVIEW PREPROCESSING PIPELINE")
    logger.info("=" * 60)
    logger.info(f"Date range: {DATE_RANGE['start']} to {DATE_RANGE['end']}")
    logger.info(f"Chunk size: {CHUNK_SIZE:,} rows")
    logger.info(f"Output directory: {PROCESSED_DATA_DIR}")
    logger.info(f"Cohort definition: grant_date ({COHORT_DATE_FIELD})")
    logger.info(f"Overwrite mode: {PREPROCESS_OVERWRITE}")
    logger.info("")

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        _assert_metadata_or_raise()
    except RuntimeError as e:
        logger.error(str(e))
        return

    valid_patents = process_patent_file()

    if not valid_patents:
        logger.error("No valid patents found! Check date range and input file.")
        return

    application_rows = process_application_file(valid_patents)
    claims_rows = process_claims_files(valid_patents)
    other_results = process_other_files(valid_patents)

    _write_metadata()

    logger.info("")
    logger.info("=" * 60)
    logger.info("PREPROCESSING COMPLETE - SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Patents (grant_date {DATE_RANGE['start']}..{DATE_RANGE['end']}): {len(valid_patents):,}")
    logger.info(f"Patent metadata rows: {_parquet_row_count(PROCESSED_FILES['patent']):,}")
    logger.info(f"Claims: {_parquet_row_count(PROCESSED_FILES['claims']):,}")
    logger.info(f"Application: {_parquet_row_count(PROCESSED_FILES['application']):,}")
    for file_key, rows in other_results.items():
        logger.info(f"{file_key.capitalize()}: {_parquet_row_count(PROCESSED_FILES[file_key]):,}")

    logger.info("")
    logger.info("Output files:")
    for output_file in sorted(PROCESSED_DATA_DIR.glob("*.parquet")):
        size_mb = output_file.stat().st_size / (1024 * 1024)
        logger.info(f"  {output_file.name}: {size_mb:.1f} MB")


if __name__ == "__main__":
    run_preprocessing_pipeline()
