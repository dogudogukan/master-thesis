"""
Run the patent pipeline into named snapshots and archive existing outputs.

This wrapper keeps the working tree under results/, writes immutable named
runs under runs/, and updates the latest symlink so downstream
work can use a stable path without losing older runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJECT_ROOT / "runs"
RESULTS_ROOT = PROJECT_ROOT / "results"
STAGE_DIRS = ["01_matches", "02_blockchain_patents", "03_final", "04_plots"]

PREPROCESS_SCRIPT = PROJECT_ROOT / "src" / "database_preparation" / "preprocess_patents.py"
EXTRACT_SCRIPT = (
    PROJECT_ROOT
    / "src"
    / "identification_of_blockchain_patents"
    / "extract_blockchain_patents.py"
)
ASSIGNEES_SCRIPT = (
    PROJECT_ROOT
    / "src"
    / "identification_of_blockchain_patents"
    / "extract_blockchain_assignees.py"
)
BANK_DATASET_SCRIPT = (
    PROJECT_ROOT
    / "src"
    / "identification_of_blockchain_patents"
    / "build_bank_patent_dataset.py"
)
SUMMARY_TABLES_SCRIPT = (
    PROJECT_ROOT
    / "src"
    / "identification_of_blockchain_patents"
    / "build_bank_summary_tables.py"
)

DEFAULT_PIPELINE_STAGES = [
    ("extract", EXTRACT_SCRIPT),
    ("assignees", ASSIGNEES_SCRIPT),
    ("bank", BANK_DATASET_SCRIPT),
    ("summary", SUMMARY_TABLES_SCRIPT),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage versioned patent pipeline runs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Execute the pipeline into a named run directory.")
    run_parser.add_argument("run_name", help="Run directory name, for example 2026-03-15_full_v2")
    run_parser.add_argument(
        "--include-preprocess",
        action="store_true",
        help="Run preprocessing before the extract/assignee/bank/summary stages.",
    )
    run_parser.add_argument(
        "--preprocess-overwrite",
        action="store_true",
        help="Pass PREPROCESS_OVERWRITE=1 to the preprocessing stage.",
    )
    run_parser.add_argument("--data-dir", help="Override PATENT_DATA_DIR for the run.")
    run_parser.add_argument("--bank-mapping-csv", help="Override BANK_ASSIGNEE_MAPPING_CSV for the run.")
    run_parser.add_argument(
        "--no-update-latest",
        action="store_true",
        help="Do not update the latest symlinks after the run finishes.",
    )

    archive_parser = subparsers.add_parser(
        "archive",
        help="Snapshot an existing output tree into a named run directory.",
    )
    archive_parser.add_argument("run_name", help="Run directory name, for example 2026-03-15_full_v1")
    archive_parser.add_argument(
        "--source-root",
        default=str(RESULTS_ROOT),
        help="Existing output root to archive. Defaults to results/.",
    )
    archive_parser.add_argument("--data-dir", help="Override PATENT_DATA_DIR recorded in archive metadata.")
    archive_parser.add_argument(
        "--bank-mapping-csv",
        help="Override BANK_ASSIGNEE_MAPPING_CSV recorded in archive metadata.",
    )
    archive_parser.add_argument(
        "--no-update-latest",
        action="store_true",
        help="Do not update the latest symlinks after the archive finishes.",
    )

    return parser.parse_args()


def validate_run_name(run_name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run_name):
        raise SystemExit("Invalid run_name. Use letters, numbers, dots, underscores, or hyphens only.")
    return run_name


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_data_dir(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()

    env_data_dir = os.getenv("PATENT_DATA_DIR")
    if env_data_dir:
        return Path(env_data_dir).expanduser().resolve()

    return (PROJECT_ROOT / "data" / "processed").resolve()


def resolve_bank_mapping_csv(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()

    env_mapping_csv = os.getenv("BANK_ASSIGNEE_MAPPING_CSV")
    if env_mapping_csv:
        return Path(env_mapping_csv).expanduser().resolve()

    return (PROJECT_ROOT / "mapping" / "unique_assignees_bank_mapping.csv").resolve()


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_new_run_root(run_root: Path) -> None:
    if run_root.exists():
        raise SystemExit(f"Run directory already exists: {run_root}")
    run_root.mkdir(parents=True, exist_ok=False)


def stage_dirs_present(root: Path) -> list[str]:
    return [stage_dir for stage_dir in STAGE_DIRS if (root / stage_dir).exists()]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def snapshot_inputs(run_root: Path, data_dir: Path, bank_mapping_csv: Path) -> dict:
    """Copy the mapping file and preprocess metadata into 00_inputs/."""
    snapshot_dir = run_root / "00_inputs"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    snapshot_info: dict[str, object] = {
        "bank_mapping_csv": {
            "source_path": str(bank_mapping_csv),
            "sha256": sha256_file(bank_mapping_csv),
            "snapshot_path": None,
        },
        "preprocess_metadata": {
            "source_path": None,
            "sha256": None,
            "snapshot_path": None,
        },
    }

    if bank_mapping_csv.exists():
        bank_snapshot = snapshot_dir / bank_mapping_csv.name
        shutil.copy2(bank_mapping_csv, bank_snapshot)
        snapshot_info["bank_mapping_csv"]["snapshot_path"] = str(bank_snapshot)

    preprocess_meta = data_dir / "_preprocess_metadata.json"
    snapshot_info["preprocess_metadata"]["source_path"] = str(preprocess_meta)
    snapshot_info["preprocess_metadata"]["sha256"] = sha256_file(preprocess_meta)
    if preprocess_meta.exists():
        preprocess_snapshot = snapshot_dir / preprocess_meta.name
        shutil.copy2(preprocess_meta, preprocess_snapshot)
        snapshot_info["preprocess_metadata"]["snapshot_path"] = str(preprocess_snapshot)

    return snapshot_info


def run_command(command: list[str], env: dict[str, str], log_handle, stage_name: str) -> None:
    header = f"\n===== STAGE: {stage_name} =====\n"
    sys.stdout.write(header)
    log_handle.write(header)
    sys.stdout.flush()
    log_handle.flush()

    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(line)
        log_handle.write(line)

    return_code = process.wait()
    log_handle.flush()
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, command)


def update_latest_links(run_root: Path) -> None:
    """Point both latest symlinks at the selected run and refresh its marker file."""
    link_paths = [RUNS_ROOT / "latest", RESULTS_ROOT / "latest"]
    for link_path in link_paths:
        link_path.parent.mkdir(parents=True, exist_ok=True)
        if link_path.exists() or link_path.is_symlink():
            if not link_path.is_symlink():
                raise RuntimeError(f"Refusing to replace non-symlink path: {link_path}")
            link_path.unlink()
        relative_target = os.path.relpath(run_root, start=link_path.parent)
        link_path.symlink_to(relative_target, target_is_directory=True)

    (run_root / "LATEST_RUN.txt").write_text(f"{run_root.name}\n", encoding="utf-8")
    for legacy_marker in (RUNS_ROOT / "LATEST_RUN.txt", RESULTS_ROOT / "LATEST_RUN.txt"):
        if legacy_marker.exists():
            legacy_marker.unlink()


def make_base_metadata(run_root: Path, mode: str, data_dir: Path, bank_mapping_csv: Path) -> dict:
    return {
        "run_name": run_root.name,
        "mode": mode,
        "created_at_utc": now_utc_iso(),
        "project_root": str(PROJECT_ROOT),
        "run_root": str(run_root),
        "data_dir": str(data_dir),
        "bank_mapping_csv": str(bank_mapping_csv),
        "python_executable": sys.executable,
    }


def execute_pipeline(args: argparse.Namespace) -> Path:
    run_name = validate_run_name(args.run_name)
    run_root = RUNS_ROOT / run_name
    ensure_new_run_root(run_root)

    data_dir = resolve_data_dir(args.data_dir)
    bank_mapping_csv = resolve_bank_mapping_csv(args.bank_mapping_csv)
    log_path = run_root / "run.log"

    env = os.environ.copy()
    env["PATENT_PIPELINE_OUT_ROOT"] = str(run_root)
    env["PATENT_DATA_DIR"] = str(data_dir)
    env["BANK_ASSIGNEE_MAPPING_CSV"] = str(bank_mapping_csv)
    env["PYTHONUNBUFFERED"] = "1"

    stages: list[tuple[str, Path]] = list(DEFAULT_PIPELINE_STAGES)
    if args.include_preprocess:
        stages = [("preprocess", PREPROCESS_SCRIPT), *stages]
        if args.preprocess_overwrite:
            env["PREPROCESS_OVERWRITE"] = "1"

    metadata = make_base_metadata(run_root, "run", data_dir, bank_mapping_csv)
    metadata["requested_stages"] = [stage_name for stage_name, _ in stages]
    metadata["input_snapshots"] = snapshot_inputs(run_root, data_dir, bank_mapping_csv)
    write_json(run_root / "run_metadata.json", metadata)

    with log_path.open("w", encoding="utf-8") as log_handle:
        log_handle.write(f"Run started at {now_utc_iso()}\n")
        log_handle.write(f"Run root: {run_root}\n")
        log_handle.write(f"Data dir: {data_dir}\n")
        log_handle.write(f"Bank mapping CSV: {bank_mapping_csv}\n")
        for stage_name, script_path in stages:
            run_command([sys.executable, "-u", str(script_path)], env, log_handle, stage_name)
        log_handle.write(f"\nRun finished at {now_utc_iso()}\n")

    metadata["completed_at_utc"] = now_utc_iso()
    metadata["stage_dirs_present"] = stage_dirs_present(run_root)
    write_json(run_root / "run_metadata.json", metadata)

    if not args.no_update_latest:
        update_latest_links(run_root)

    return run_root


def archive_existing_outputs(args: argparse.Namespace) -> Path:
    run_name = validate_run_name(args.run_name)
    run_root = RUNS_ROOT / run_name
    ensure_new_run_root(run_root)

    source_root = Path(args.source_root).expanduser().resolve()
    data_dir = resolve_data_dir(args.data_dir)
    bank_mapping_csv = resolve_bank_mapping_csv(args.bank_mapping_csv)

    copied_stage_dirs = []
    for stage_dir in STAGE_DIRS:
        source_dir = source_root / stage_dir
        if source_dir.exists():
            shutil.copytree(source_dir, run_root / stage_dir)
            copied_stage_dirs.append(stage_dir)

    if not copied_stage_dirs:
        raise SystemExit(f"No known stage directories found under {source_root}")

    metadata = make_base_metadata(run_root, "archive", data_dir, bank_mapping_csv)
    metadata["archived_from"] = str(source_root)
    metadata["stage_dirs_present"] = copied_stage_dirs
    metadata["input_snapshots"] = snapshot_inputs(run_root, data_dir, bank_mapping_csv)
    write_json(run_root / "run_metadata.json", metadata)

    archive_log = (
        f"Archived existing output root at {now_utc_iso()}\n"
        f"Source root: {source_root}\n"
        f"Copied stage dirs: {', '.join(copied_stage_dirs)}\n"
    )
    (run_root / "run.log").write_text(archive_log, encoding="utf-8")

    if not args.no_update_latest:
        update_latest_links(run_root)

    return run_root


def main() -> None:
    args = parse_args()
    if args.command == "run":
        run_root = execute_pipeline(args)
        print(f"Created run: {run_root}")
        return

    if args.command == "archive":
        run_root = archive_existing_outputs(args)
        print(f"Archived run: {run_root}")
        return

    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
