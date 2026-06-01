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

try:  # package normally defines this; be resilient to namespace-package resolution on some hosts
    from . import __version__
except ImportError:  # pragma: no cover
    __version__ = "0.0.0"
from .config import SUPPORTED_TYPES, SUPPORTED_VENDORS, build_config, parse_csv
from .stages.fmc_combine_data import run_fmc_combine_data
from .stages.full_mc_parse_and_normalize import run_full_mc_parse_and_normalize
from .stages.get_pr_sigma import run_build_pr_table
from .stages.lib_join_sigma import run_lib_join_sigma

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
        "planned_pr": "removed",
        "note": "Full MC removed (G4); moments now derived from FMC data.",
    },
    {
        "stage": "lib_join",
        "pipeline": "sigma,moments",
        "implemented": True,
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
        "stage": "build_pr_table",
        "pipeline": "sigma",
        "implemented": False,
        "planned_pr": "PR 6",
    },
    {
        "stage": "get_pr_moments",
        "pipeline": "moments",
        "implemented": True,
        "planned_pr": "PR 7",
        "note": "Moments (meanshift/std/skew) Base_PR + Waiver1 from FMC RPT; no Full MC.",
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
    parser.add_argument("--fmc-golden-dir", help="FMC deck directory (mode=decks). Enables the Sigma pipeline.")
    parser.add_argument(
        "--fmc-mode",
        choices=("decks", "parsed_dfds", "parsed_scld"),
        default="decks",
        help="FMC input mode: decks (parse decks), parsed_dfds (already-parsed DFDS tables), parsed_scld (SCLD files).",
    )
    parser.add_argument(
        "--fmc-input-dir",
        help="Directory of already-parsed FMC tables (required for --fmc-mode parsed_dfds/parsed_scld).",
    )
    parser.add_argument(
        "--full-mc-golden-dir",
        help="Full MC simulation directory. Enables the Moments pipeline when provided.",
    )
    parser.add_argument(
        "--vt-type",
        default="",
        help="Optional VT type (e.g. svt, elvt). Batch metadata; also disambiguates parsed FMC files when set.",
    )
    parser.add_argument(
        "--rc-type",
        default="",
        help="Optional RC type (e.g. cworst, cbest, typical). Batch metadata; also disambiguates parsed FMC files.",
    )
    parser.add_argument(
        "--library-type",
        choices=("auto", "base", "mb"),
        default="auto",
        help="Library structure hint: base, mb (multi-bit), or auto. Metadata only; lib-join is always bundle-aware.",
    )
    parser.add_argument("--lib-dir", required=True, help="Directory containing .lib files.")
    parser.add_argument("--output-dir", required=True, help="Output directory for stable artifacts.")
    parser.add_argument(
        "--full-mc-keep-raw-samples",
        action="store_true",
        help="Phase 2/3 option placeholder: keep raw Full MC samples in addition to summary and histogram bins.",
    )
    parser.add_argument(
        "--enable-full-mc",
        action="store_true",
        help="Run Full MC pipeline now. By default it is deferred while FMC flow is prioritized.",
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


def write_manifests(config, stage_execution=None, compatibility_stage_reports=None, audit_summary=None) -> None:
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
        "audit_summary": audit_summary or {},
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
    with log_file.open("a", encoding="utf-8") as f:
        f.write("stage_summary:\n")
        for st in stage_execution:
            f.write(
                f"  stage={st.get('stage','unknown')} status={st.get('status','unknown')} "
                f"pipeline={st.get('pipeline','unknown')} reason={st.get('reason','')}\n"
            )


def _announce_stage(stage: dict) -> None:
    name = stage.get("stage", "unknown")
    status = stage.get("status", "unknown")
    reason = stage.get("reason", "")
    msg = f"[{name}] {status}"
    if reason:
        msg += f" ({reason})"
    print(msg)
    if stage.get("log_file"):
        print(f"[{name}] log_file={stage['log_file']}")
    failures = stage.get("failures") or []
    if failures:
        print(f"[{name}] failures={len(failures)} first_reason={failures[0].get('reason','unknown')}")
    if stage.get("failure_summary"):
        fs = stage["failure_summary"]
        print(
            f"[{name}] failure_summary=count:{fs.get('count', 0)} "
            f"partial_success:{fs.get('has_partial_success', False)}"
        )


def _record_stage(stage_execution: list, compatibility_stage_reports: list, result_obj) -> bool:
    stage_execution.append(result_obj.stage_execution)
    compatibility_stage_reports.append(result_obj.compatibility_stage_report)
    _announce_stage(result_obj.stage_execution)
    return result_obj.failed


def execute_stages(config, on_stage=None, on_finding=None):
    """Run the pipeline stages for one config; shared by the CLI and web executor.

    ``on_stage(stage_dict)`` is invoked as each stage starts (status='running') and
    again when it completes, so a live UI can track progress.
    ``on_finding(stage_name, finding_dicts)`` is invoked after each stage completes
    with any high-signal audit findings for that stage.
    Returns ``(stage_execution, compatibility_stage_reports, failed)``.
    """

    from . import audit
    from .stages.get_pr_moments import run_get_pr_moments
    from .stages.pr_web_app import run_generate_pr_web_app

    materialize_output_tree(config.output_dir)
    stage_execution: list = []
    compatibility_stage_reports: list = []
    all_findings: list = []
    failed = False

    def _audit(result) -> None:
        se = result.stage_execution
        log_text = ""
        lf = se.get("log_file")
        if lf:
            try:
                from pathlib import Path as _P
                log_text = _P(lf).read_text(encoding="utf-8", errors="replace")
            except OSError:
                log_text = ""
        findings = audit.audit_stage(se, log_text)
        dicts = audit.findings_to_dicts(findings)
        all_findings.extend(dicts)
        if on_finding and dicts:
            on_finding(se.get("stage", "?"), dicts)

    def _running(name: str, pipeline: str) -> None:
        if on_stage:
            on_stage({"stage": name, "status": "running", "pipeline": pipeline, "reason": ""})

    def _done(result) -> None:
        nonlocal failed
        failed = _record_stage(stage_execution, compatibility_stage_reports, result) or failed
        if on_stage:
            on_stage(result.stage_execution)
        _audit(result)

    if config.run_sigma:
        # Full MC is removed (G4): moments are derived from FMC data below.
        # FMC input is mode-aware: parse decks, or ingest already-parsed DFDS/SCLD tables.
        _running("fmc_combine_data", "sigma")
        print(f"[fmc_combine_data] running (mode={config.fmc_mode})")
        if config.fmc_mode == "decks":
            _done(run_fmc_combine_data(config))
        else:
            from .stages.fmc_ingest_parsed import run_fmc_ingest_parsed
            _done(run_fmc_ingest_parsed(config))

        _running("lib_join_sigma", "sigma")
        print("[lib_join_sigma] running")
        _done(run_lib_join_sigma(config))

        _running("build_pr_table", "sigma")
        print("[build_pr_table] running")
        _done(run_build_pr_table(config))

        _running("get_pr_moments", "moments")
        print("[get_pr_moments] running")
        _done(run_get_pr_moments(config))
    else:
        skipped = {
            "stage": "build_pr_table",
            "pipeline": "sigma,moments",
            "status": "skipped",
            "reason": "requires_fmc_inputs",
        }
        stage_execution.append(skipped)
        _announce_stage(skipped)
        if on_stage:
            on_stage(skipped)

    _done(run_generate_pr_web_app(config, stage_execution))
    try:
        audit.write_report(all_findings, config.output_dir / "logs" / "audit_report.txt")
    except OSError:
        pass
    write_manifests(config, stage_execution, compatibility_stage_reports,
                    audit_summary=audit.summarize(all_findings))
    return stage_execution, compatibility_stage_reports, failed


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
            fmc_mode=args.fmc_mode,
            fmc_input_dir=args.fmc_input_dir,
            vt_type=args.vt_type,
            rc_type=args.rc_type,
            library_type=args.library_type,
        )
    except ValueError as exc:
        parser.error(str(exc))

    _stages, _compat, failed = execute_stages(config)
    print(f"Initialized cert_data_process output tree at: {config.output_dir}")
    return 1 if failed else 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Console-script entry point."""

    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
