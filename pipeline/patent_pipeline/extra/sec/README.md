# SEC

This folder keeps exploratory SEC-side work for possible external-use and
licensing signals.

What it does:

- builds bank- and patent-level SEC target lists from the current patent sample
- caches SEC submission JSON files and filing documents
- scans local filings for exact patent/application mentions and broad keyword hits

Main inputs:

- `config/sec_issuer_seed.csv`
- `raw/sec_filings/`
- `raw/sec_submissions/`

Main scripts:

- `scripts/build_sec_targets.py`
- `scripts/cache_sec_submissions.py`
- `scripts/build_sec_filing_manifest.py`
- `scripts/download_sec_filings.py`
- `scripts/scan_local_sec_filings.py`

Main outputs:

- `results/sec_patent_targets.csv`
- `results/sec_bank_targets.csv`
- `results/sec_download_plan.csv`
- `results/sec_filing_manifest.csv`
- `results/sec_exact_hits.csv`
- `results/sec_keyword_file_hits.csv`
- `results/sec_findings.txt`

Output roles:

- `sec_patent_targets.csv`, `sec_bank_targets.csv`, `sec_download_plan.csv`
  Targeting and collection tables.
- `sec_filing_manifest.csv`
  Filing-level download manifest built from cached SEC submissions.
- `sec_exact_hits.csv`
  Exact patent/application mentions found in local filing text.
- `sec_keyword_file_hits.csv`
  Broad keyword-level file hits used for exploratory review.
- `sec_findings.txt`
  Short note on current coverage and interpretation.

Usage:

```bash
.venv/bin/python pipeline/patent_pipeline/extra/sec/scripts/build_sec_targets.py

.venv/bin/python pipeline/patent_pipeline/extra/sec/scripts/scan_local_sec_filings.py
```

Notes:

- The default patent sample source is `pipeline/patent_pipeline/results/latest/03_final/patents.csv`.
- The default application table source is `pipeline/patent_pipeline/data/processed/g_application.parquet`.
- SEC work here is exploratory and remains outside the core patent pipeline.
- Current analysis does not depend directly on the SEC outputs in this folder.
