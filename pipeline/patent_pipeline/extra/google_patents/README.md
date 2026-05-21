# Google Patents

This folder captures Google Patents pages for the current patent sample and
extracts sidecar information that does not come directly from PatentsView.

What it does:

- builds a manifest from the latest patent-pipeline result set
- saves Google Patents pages as PDF and HTML
- extracts legal events and worldwide application sidecars

Main scripts:

- `scripts/build_google_patents_manifest.py`
- `scripts/capture_google_patents_pages.py`
- `scripts/build_legal_event_summaries.py`

Main outputs:

- `results/google_patents_manifest.tsv`
- `results/google_patents_summary.csv`
- `results/google_patents_legal_event_patent_flags.csv`
- `results/google_patents_legal_event_bank_summary.csv`
- `results/google_patents_legal_event_codebook.csv`
- `results/google_patents_legal_event_watchlist.csv`
- `raw/google_patents_pdf/*.pdf`
- `raw/google_patents_html/*.html`
- `raw/google_patents_legal_events/*.json`

Output roles:

- `google_patents_legal_event_patent_flags.csv`
  Main analysis-ready file. This is the output used in later feature
  construction.
- `google_patents_summary.csv`
  Capture coverage and error summary.
- `google_patents_legal_event_bank_summary.csv`,
  `google_patents_legal_event_codebook.csv`,
  `google_patents_legal_event_watchlist.csv`
  Diagnostic and interpretation tables.

Usage:

```bash
python3 pipeline/patent_pipeline/extra/google_patents/scripts/build_google_patents_manifest.py

python3 pipeline/patent_pipeline/extra/google_patents/scripts/capture_google_patents_pages.py \
  --limit 5
```

Notes:

- The default manifest source is `pipeline/patent_pipeline/results/latest/03_final/patents.csv`.
- Google Patents is used as an enrichment source rather than the primary
  official source.
- The current analysis uses `google_patents_legal_event_patent_flags.csv`
  rather than the raw HTML, PDF, or JSON files directly.
