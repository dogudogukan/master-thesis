"""
Processing settings used in preprocessing.

The main methodological choice here is the grant-date cohort window. The other
settings are practical read/write defaults for the local pipeline.
"""

# Chunk size used in the raw TSV reads.
CHUNK_SIZE = 1_000_000

# Grant-date cohort window.
DATE_RANGE = {
    "start": "2008-01-01",
    "end": "2025-12-31",
}

# Parquet compression used in the processed outputs.
PARQUET_COMPRESSION = "snappy"

# Text values treated as missing on import.
NA_VALUES = ["", "NA", "None", "NULL"]
