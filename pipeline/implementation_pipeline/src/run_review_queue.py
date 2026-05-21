"""
Build the implementation review queue into results/ and archive named runs.

This wrapper keeps the active working tree under results/, writes immutable
named snapshots under runs/, and updates latest symlinks after each archived
run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE_A_DATA_DIR = REPO_ROOT / "data" / "phase_a"
RESULTS_ROOT = REPO_ROOT / "results"
RUNS_ROOT = REPO_ROOT / "runs"

from review_queue_workflow import run_pipeline


def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value).expanduser() if value else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage implementation review-queue runs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--data-dir",
        type=Path,
        default=_env_path("IMPLEMENTATION_DATA_DIR", PHASE_A_DATA_DIR),
    )
    common.add_argument(
        "--config",
        type=Path,
        default=_env_path("IMPLEMENTATION_BANK_CONFIG", REPO_ROOT / "config" / "banks.json"),
    )
    common.add_argument(
        "--output-root",
        type=Path,
        default=_env_path("IMPLEMENTATION_PIPELINE_OUT_ROOT", RESULTS_ROOT),
    )
    common.add_argument("--review-count", type=int, default=_env_int("IMPLEMENTATION_REVIEW_COUNT", 400))
    common.add_argument("--max-files-per-source", type=int, default=None)
    common.add_argument("--bw-article-limit", type=int, default=None)
    common.add_argument(
        "--sources",
        nargs="+",
        choices=["american_banker", "pr_newswire", "business_wire"],
        default=None,
        help="Restrict the run to one or more source folders.",
    )

    subparsers.add_parser(
        "build",
        parents=[common],
        help="Build the active review queue under results/.",
    )

    run_parser = subparsers.add_parser(
        "run",
        parents=[common],
        help="Build results/ and archive them into a named run directory.",
    )
    run_parser.add_argument("run_name", help="Run directory name, for example full_v4")
    run_parser.add_argument(
        "--runs-root",
        type=Path,
        default=_env_path("IMPLEMENTATION_RUNS_ROOT", RUNS_ROOT),
        help="Run archive root. Defaults to runs/.",
    )
    run_parser.add_argument(
        "--no-update-latest",
        action="store_true",
        help="Do not update the latest symlinks after the run finishes.",
    )

    archive_parser = subparsers.add_parser(
        "archive",
        help="Snapshot an existing working results tree into a named run directory.",
    )
    archive_parser.add_argument("run_name", help="Run directory name, for example full_v4")
    archive_parser.add_argument(
        "--source-root",
        type=Path,
        default=_env_path("IMPLEMENTATION_PIPELINE_OUT_ROOT", RESULTS_ROOT),
        help="Existing output root to archive. Defaults to results/.",
    )
    archive_parser.add_argument(
        "--config",
        type=Path,
        default=_env_path("IMPLEMENTATION_BANK_CONFIG", REPO_ROOT / "config" / "banks.json"),
    )
    archive_parser.add_argument(
        "--runs-root",
        type=Path,
        default=_env_path("IMPLEMENTATION_RUNS_ROOT", RUNS_ROOT),
        help="Run archive root. Defaults to runs/.",
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


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def ensure_new_run_root(run_root: Path) -> None:
    if run_root.exists():
        raise SystemExit(f"Run directory already exists: {run_root}")
    run_root.mkdir(parents=True, exist_ok=False)


def snapshot_inputs(run_root: Path, config_path: Path) -> dict:
    snapshot_dir = run_root / "00_inputs"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    snapshot_info: dict[str, object] = {
        "bank_config": {
            "source_path": str(config_path),
            "sha256": sha256_file(config_path),
            "snapshot_path": None,
        }
    }

    if config_path.exists():
        config_snapshot = snapshot_dir / config_path.name
        shutil.copy2(config_path, config_snapshot)
        snapshot_info["bank_config"]["snapshot_path"] = str(config_snapshot)

    return snapshot_info


def copy_output_tree(source_root: Path, run_root: Path) -> list[str]:
    copied_entries: list[str] = []
    for path in sorted(source_root.iterdir(), key=lambda item: item.name):
        if path.name in {"latest", "LATEST_RUN.txt"}:
            continue
        target = run_root / path.name
        if path.is_dir():
            shutil.copytree(path, target)
        elif path.is_file():
            shutil.copy2(path, target)
        else:
            continue
        copied_entries.append(path.name)
    return copied_entries


def update_latest_links(run_root: Path, results_root: Path, runs_root: Path) -> None:
    link_paths = [runs_root / "latest", results_root / "latest"]
    for link_path in link_paths:
        link_path.parent.mkdir(parents=True, exist_ok=True)
        if link_path.exists() or link_path.is_symlink():
            if not link_path.is_symlink():
                raise RuntimeError(f"Refusing to replace non-symlink path: {link_path}")
            link_path.unlink()
        relative_target = os.path.relpath(run_root, start=link_path.parent)
        link_path.symlink_to(relative_target, target_is_directory=True)

    (run_root / "LATEST_RUN.txt").write_text(f"{run_root.name}\n", encoding="utf-8")
    for marker in (runs_root / "LATEST_RUN.txt", results_root / "LATEST_RUN.txt"):
        if marker.exists():
            marker.unlink()


def make_base_metadata(
    mode: str,
    output_root: Path,
    run_root: Path,
    data_dir: Path,
    config_path: Path,
) -> dict:
    return {
        "run_name": run_root.name,
        "mode": mode,
        "created_at_utc": now_utc_iso(),
        "project_root": str(REPO_ROOT),
        "output_root": str(output_root),
        "run_root": str(run_root),
        "data_dir": str(data_dir),
        "config_path": str(config_path),
        "python_executable": sys.executable,
    }


def execute_build(args: argparse.Namespace) -> dict[str, object]:
    summary = run_pipeline(
        data_dir=args.data_dir,
        config_path=args.config,
        output_dir=args.output_root,
        repo_root=REPO_ROOT,
        review_count=args.review_count,
        max_files_per_source=args.max_files_per_source,
        bw_article_limit=args.bw_article_limit,
        sources=args.sources,
    )
    return summary


def execute_run(args: argparse.Namespace) -> Path:
    run_name = validate_run_name(args.run_name)
    run_root = args.runs_root / run_name
    ensure_new_run_root(run_root)

    summary = execute_build(args)
    copied_entries = copy_output_tree(args.output_root, run_root)
    metadata = make_base_metadata("run", args.output_root, run_root, args.data_dir, args.config)
    metadata["summary"] = summary
    metadata["copied_entries"] = copied_entries
    metadata["input_snapshots"] = snapshot_inputs(run_root, args.config)
    write_json(run_root / "run_metadata.json", metadata)

    run_log = (
        f"Run started at {metadata['created_at_utc']}\n"
        f"Output root: {args.output_root}\n"
        f"Data dir: {args.data_dir}\n"
        f"Config: {args.config}\n"
        f"Copied entries: {', '.join(copied_entries)}\n"
        f"Run finished at {now_utc_iso()}\n"
    )
    (run_root / "run.log").write_text(run_log, encoding="utf-8")

    if not args.no_update_latest:
        update_latest_links(run_root, args.output_root, args.runs_root)

    return run_root


def execute_archive(args: argparse.Namespace) -> Path:
    run_name = validate_run_name(args.run_name)
    run_root = args.runs_root / run_name
    ensure_new_run_root(run_root)

    if not args.source_root.exists():
        raise SystemExit(f"Source root does not exist: {args.source_root}")
    copied_entries = copy_output_tree(args.source_root, run_root)
    if not copied_entries:
        raise SystemExit(f"No output files found under {args.source_root}")

    metadata = make_base_metadata("archive", args.source_root, run_root, PHASE_A_DATA_DIR, args.config)
    metadata["archived_from"] = str(args.source_root)
    metadata["copied_entries"] = copied_entries
    metadata["input_snapshots"] = snapshot_inputs(run_root, args.config)
    write_json(run_root / "run_metadata.json", metadata)

    archive_log = (
        f"Archived existing output root at {now_utc_iso()}\n"
        f"Source root: {args.source_root}\n"
        f"Copied entries: {', '.join(copied_entries)}\n"
    )
    (run_root / "run.log").write_text(archive_log, encoding="utf-8")

    if not args.no_update_latest:
        update_latest_links(run_root, args.source_root, args.runs_root)

    return run_root


def main() -> int:
    args = parse_args()
    if args.command == "build":
        summary = execute_build(args)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    if args.command == "run":
        run_root = execute_run(args)
        print(f"Created run: {run_root}")
        return 0

    if args.command == "archive":
        run_root = execute_archive(args)
        print(f"Archived run: {run_root}")
        return 0

    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
