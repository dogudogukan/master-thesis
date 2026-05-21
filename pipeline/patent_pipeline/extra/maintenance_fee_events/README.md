# Maintenance Fee Events

This folder turns the USPTO maintenance-fee event dump into patent-level
features for later analysis.

What it does:

- reads the latest raw maintenance archive under `raw/`
- normalizes the USPTO event codes
- collapses raw event rows to one patent-level feature row

Main script:

- `scripts/build_maintenance_fee_patent_features.py`

Main outputs:

- `results/maintenance_fee_patent_features.parquet`
- `results/maintenance_fee_codebook.csv`
- `results/maintenance_fee_findings.txt`

Output roles:

- `maintenance_fee_patent_features.parquet`
  Main analysis-ready file. This is the output used in later feature
  construction.
- `maintenance_fee_codebook.csv`
  Compact event-code reference table.
- `maintenance_fee_findings.txt`
  Short note on coverage and interpretation.

Usage:

```bash
.venv/bin/python \
  pipeline/patent_pipeline/extra/maintenance_fee_events/scripts/build_maintenance_fee_patent_features.py
```

Notes:

- The raw archive stays under `raw/`; later analysis uses the patent-level
  file in `results/`.
- This source is separate from the main PatentsView pipeline because it is a
  later patent-feature input rather than an extraction input.
