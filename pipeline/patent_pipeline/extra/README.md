# Extra Sources

This folder keeps source-specific sidecar work outside the core patent
pipeline.

Current subdirectories:

- `google_patents/`
  Google Patents page capture, legal-event parsing, and worldwide-family
  sidecars.
- `sec/`
  SEC filing target generation, downloads, and local filing scans.
- `maintenance_fee_events/`
  USPTO maintenance-fee events turned into patent-level renewal features.
- `assignment/`
  USPTO assignment files and assignment-side exploratory scans.

Common pattern:

- `raw/`
  Source files kept in their original downloaded form.
- `scripts/`
  Source-specific helpers that turn raw files into usable outputs.
- `results/`
  Derived outputs meant for later review or analysis.

One exception:

- `sec/` also has `config/` because issuer seeds are curated rather than
  downloaded.

These sources are optional extensions. The main blockchain-bank patent sample
is still built from PatentsView data under `data/` and the curated bank
mapping under `mapping/`.
