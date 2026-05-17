"""Command-line entry point for cert_data_process.

This first Phase 1 skeleton intentionally creates only the run directory
structure and manifests. Functional stage implementations land in follow-up PRs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from . import __version__
from .config import SUPPORTED_TYPES, SUPPORTED_VENDORS, build_config, parse_csv
from .stages.fmc_combine_data import run_fmc_combine_data

OUTPUT_DIRECTORIES = (
    "logs",
    "normalized/fmc",
    "normalized/full_mc",
    "combined/sigma",
    "combined/moments",
    "ci_validation/sigma",
    "ci_validation/moments",
    "pr/sigma",
    "pr/moments",
    "debug/full_mc",
)

PLANNED_STAGE_STATUS = (
    {
        "stage": "fmc_combine_data",
        "pipeline": "sigma",
        "implemented": True,
        "planned_pr": "PR 2",
    },
    {
        "stage": "full_mc_parse_and_normalize",
        "pipeline": "moments",
        "implemented": False,
        "planned_pr": "PR 3",
    },
    {
        "stage": "lib_join",
        "pipeline": "sigma,moments",
        "implemented": False,
        "planned_pr": "PR 4",
        "note": "Unified lib lookup core with sigma + moments output formatters",
    },
    {
        "stage": "validate_ci",
        "pipeline": "sigma,moments",
        "implemented": False,
        "planned_pr": "PR 5",
    },
    {
        "stage": "get_pr_sigma",
        "pipeline": "sigma",
        "implemented": False,
        "planned_pr": "PR 6",
    },
    {
        "stage": "get_pr_moments",
        "pipeline": "moments",
        "implemented": False,
        "planned_pr": "PR 7",
    },
)


def _run_git_command(args: list[str]) -> Optional[str]:
    """Run a git command and return stripped stdout, or None on failure."""

    try:
        completed = subprocess.run(
            ["git", *args],
            check=True,
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def _get_git_sha() -> str:
    """Return the current short git SHA, with a dirty suffix when applicable."""

    sha = _run_git_command(["rev-parse", "--short", "HEAD"])
    if not sha:
        return "unknown"

    status = _run_git_command(["status", "--porcelain"])
    if status:
        return f"{sha}-dirty"
    return sha


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(
        prog="cert_data_process",
        description="Package skeleton for the library certification data_process pipeline.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--vendor", required=True, choices=SUPPORTED_VENDORS, help="Library vendor: cdns or snps.")
    parser.add_argument("--process", required=True, help="Process name, e.g. n2p.")
    parser.add_argument("--process-version", required=True, help="Process version, e.g. v1p0.")
    parser.add_argument("--corners", required=True, help="Comma-separated corner list.")
    parser.add_argument(
        "--types",
        required=True,
        help=f"Comma-separated type list. Supported values: {', '.join(SUPPORTED_TYPES)}.",
    )
    parser.add_argument("--fmc-golden-dir", help="FMC log directory. Enables the Sigma pipeline when provided.")
    parser.add_argument(
        "--full-mc-golden-dir",
        help="Full MC simulation directory. Enables the Moments pipeline when provided.",
    )
    parser.add_argument("--lib-dir", required=True, help="Directory containing .lib files.")
    parser.add_argument("--output-dir", required=True, help="Output directory for stable artifacts.")
    parser.add_argument(
        "--full-mc-keep-raw-samples",
        action="store_true",
        help="Phase 2/3 option placeholder: keep raw Full MC samples in addition to summary and histogram bins.",
    )
    return parser


def materialize_output_tree(output_dir: Path) -> None:
    """Create the Phase 1 skeleton output directory tree."""

    output_dir.mkdir(parents=True, exist_ok=True)
    for relative_dir in OUTPUT_DIRECTORIES:
        (output_dir / relative_dir).mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict) -> None:
    """Write a deterministic, human-readable JSON file."""

    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_manifests(config, stage_execution=None, compatibility_stage_reports=None) -> None:
    """Write run and compatibility manifests."""

    output_dir = config.output_dir
    timestamp = datetime.now(timezone.utc).isoformat()
    enabled_pipelines = []
    if config.run_sigma:
        enabled_pipelines.append("sigma")
    if config.run_moments:
        enabled_pipelines.append("moments")

    stage_execution = list(stage_execution or [])
    compatibility_stage_reports = list(compatibility_stage_reports or [])

    run_manifest = {
        "schema_version": 1,
        "tool": "cert_data_process",
        "tool_version": __version__,
        "tool_git_commit_sha": _get_git_sha(),
        "created_at_utc": timestamp,
        "phase": "phase1",
        "config": config.to_manifest_dict(),
        "enabled_pipelines": enabled_pipelines,
        "output_directories": list(OUTPUT_DIRECTORIES),
        "aliases": [],
        "planned_stages": list(PLANNED_STAGE_STATUS),
        "stage_execution": stage_execution,
        "note": "Functional stages execute only when implemented for the requested pipeline inputs.",
    }
    write_json(output_dir / "run_manifest.json", run_manifest)

    compatibility_report = {
        "schema_version": 1,
        "created_at_utc": timestamp,
        "phase": "phase1",
        "diffs": [],
        "stage_reports": compatibility_stage_reports,
        "signoff_required": "Each non-byte-identical diff must be listed with root cause, fix path, and signoff status.",
        "note": "Runtime compatibility fixture comparison is not evaluated unless a stage/test supplies expected artifacts.",
    }
    write_json(output_dir / "compatibility_report.json", compatibility_report)

    log_file = output_dir / "logs" / "cert_data_process.log"
    log_file.write_text(
        "cert_data_process Phase 1 run\n"
        f"created_at_utc={timestamp}\n"
        f"enabled_pipelines={','.join(enabled_pipelines)}\n"
        f"functional_stages_executed={len(stage_execution)}\n",
        encoding="utf-8",
    )


def run(argv: Optional[Iterable[str]] = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = build_config(
            vendor=args.vendor,
            process=args.process,
            process_version=args.process_version,
            corners=parse_csv(args.corners, field_name="corners"),
            types=parse_csv(args.types, field_name="types"),
            fmc_golden_dir=args.fmc_golden_dir,
            full_mc_golden_dir=args.full_mc_golden_dir,
            lib_dir=args.lib_dir,
            output_dir=args.output_dir,
            full_mc_keep_raw_samples=args.full_mc_keep_raw_samples,
        )
    except ValueError as exc:
        parser.error(str(exc))

    materialize_output_tree(config.output_dir)

    stage_execution = []
    compatibility_stage_reports = []
    failed = False
    if config.run_sigma:
        fmc_result = run_fmc_combine_data(config)
        stage_execution.append(fmc_result.stage_execution)
        compatibility_stage_reports.append(fmc_result.compatibility_stage_report)
        failed = failed or fmc_result.failed

    write_manifests(config, stage_execution, compatibility_stage_reports)
    print(f"Initialized cert_data_process output tree at: {config.output_dir}")
    return 1 if failed else 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Console-script entry point."""

    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
