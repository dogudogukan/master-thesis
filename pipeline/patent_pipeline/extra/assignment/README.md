# Assignment

This folder holds USPTO Patent Assignment files and assignment-side exploratory
work.

Current role:

- keep the downloaded assignment source files in one place
- scan assignment records for the current patent sample
- check whether assignment text contains direct licensing or similar signals

Layout:

- `raw/`
  Downloaded assignment source files.
- `scripts/`
  Helpers for sample-level assignment scans.
- `results/`
  Sample-level assignment hits and patent flags built from the raw XML files.

This source remains outside the main pipeline because it is an optional sidecar
for later feature work rather than a required input for the blockchain-bank
sample.
