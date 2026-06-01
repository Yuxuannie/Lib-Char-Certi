"""PR table stage wrapper using legacy check_sigma.py."""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cert_data_process.config import CertDataProcessConfig


@dataclass(frozen=True)
class PrTableResult:
    stage_execution: dict[str, Any]
    compatibility_stage_report: dict[str, Any]

    @property
    def failed(self) -> bool:
        return self.stage_execution["status"] == "failed"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_build_pr_table(config: CertDataProcessConfig) -> PrTableResult:
    started_at = _utc_now()
    t0 = time.monotonic()

    output_dir = config.output_dir.resolve()
    root_path = (output_dir / "combined" / "sigma").resolve()
    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "2-data_process/get_PR/Sigma/check_sigma_with_waivers.py").resolve()
    pr_dir = (output_dir / "pr" / "sigma").resolve()
    pr_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "python3",
        str(script),
        "--root_path",
        str(root_path),
        "--corners",
        *list(config.corners),
        "--types",
        *[t for t in config.types if t in {"delay", "slew", "hold", "mpw"}],
        "--log_level",
        "INFO",
    ]

    logs_dir = (output_dir / "logs").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_log = logs_dir / "build_pr_table.log"
    log_lines = [
        "stage=build_pr_table",
        f"started_at_utc={started_at}",
        f"repo_root={repo_root}",
        f"root_path={root_path}",
        f"script={script}",
        f"script_exists={script.is_file()}",
        f"requested_corners={','.join(config.corners)}",
        f"requested_types={','.join([t for t in config.types if t in {'delay','slew','hold','mpw'}])}",
        f"cmd={' '.join(cmd)}",
        "",
    ]

    if not script.is_file():
        stage = {
            "stage": "build_pr_table",
            "pipeline": "sigma",
            "status": "failed",
            "reason": "missing_check_sigma_script",
            "started_at_utc": started_at,
            "ended_at_utc": _utc_now(),
            "duration_seconds": round(time.monotonic() - t0, 6),
            "root_path": str(root_path),
            "script": str(script),
            "command": " ".join(cmd),
            "log_file": str(run_log),
            "failures": [
                {
                    "reason": "missing_check_sigma_script",
                    "detail": f"PR table script not found: {script}",
                }
            ],
        }
        log_lines.append(f"result=failed reason=missing_check_sigma_script script={script}")
        run_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        return PrTableResult(stage, {"stage": "build_pr_table", "status": "not_evaluated", "reason": "check_sigma.py script missing; stage failed."})

    if not root_path.is_dir():
        stage = {
            "stage": "build_pr_table",
            "pipeline": "sigma",
            "status": "skipped",
            "started_at_utc": started_at,
            "ended_at_utc": _utc_now(),
            "duration_seconds": round(time.monotonic() - t0, 6),
            "root_path": str(root_path),
            "command": " ".join(cmd),
            "failures": [
                {
                    "reason": "missing_sigma_combined_dir",
                    "detail": f"Sigma RPT input directory not found; skipping pass-rate stage: {root_path}",
                }
            ],
        }
        log_lines.append("result=skipped reason=missing_sigma_combined_dir")
        run_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        return PrTableResult(stage, {"stage": "build_pr_table", "status": "not_evaluated", "reason": "No sigma combined inputs found; stage skipped."})


    rpt_candidates = [f for f in root_path.iterdir() if f.is_file() and f.suffix == ".rpt" and "fmc" in f.name.lower()]
    if not rpt_candidates:
        stage = {
            "stage": "build_pr_table",
            "pipeline": "sigma",
            "status": "skipped",
            "started_at_utc": started_at,
            "ended_at_utc": _utc_now(),
            "duration_seconds": round(time.monotonic() - t0, 6),
            "root_path": str(root_path),
            "command": " ".join(cmd),
            "failures": [],
            "reason": "no_sigma_rpt_inputs",
        }
        log_lines.append("result=skipped reason=no_sigma_rpt_inputs")
        run_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        return PrTableResult(stage, {"stage": "build_pr_table", "status": "not_evaluated", "reason": "No sigma RPT files found; stage skipped."})
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    log_lines.extend(
        [
            f"exit_code={proc.returncode}",
            "",
            "STDOUT",
            proc.stdout,
            "",
            "STDERR",
            proc.stderr,
            "",
            f"result={'passed' if proc.returncode == 0 else 'failed'}",
        ]
    )
    # Collect the PR deliverables into the dedicated pr/sigma directory so results
    # are not buried among intermediate files in combined/sigma.
    pr_deliverables = [
        "sigma_PR_table_with_waivers.csv",
        "sigma_waiver_summary_table.txt",
        "optimistic_pessimistic_breakdown.txt",
        "sigma_pass_rate_visualization.png",
    ]
    copied = []
    for name in pr_deliverables:
        src = root_path / name
        if src.is_file():
            dst = pr_dir / name
            shutil.copy2(src, dst)
            copied.append(str(dst))
    log_lines.append("")
    log_lines.append("pr_sigma_outputs:")
    for c in copied:
        log_lines.append(f"  {c}")
    run_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    # Surface the PR table on the terminal so the user does not have to dig in the log.
    pr_table = pr_dir / "sigma_PR_table_with_waivers.csv"
    print(f"[build_pr_table] PR outputs copied to: {pr_dir}")
    if pr_table.is_file():
        try:
            text = pr_table.read_text(encoding="utf-8")
            print("[build_pr_table] sigma_PR_table_with_waivers.csv:")
            for line in text.splitlines():
                print(f"    {line}")
        except OSError:
            pass
    else:
        print("[build_pr_table] WARNING: sigma_PR_table_with_waivers.csv not produced (see build_pr_table.log)")

    stage = {
        "stage": "build_pr_table",
        "pipeline": "sigma",
        "status": "passed" if proc.returncode == 0 else "failed",
        "started_at_utc": started_at,
        "ended_at_utc": _utc_now(),
        "duration_seconds": round(time.monotonic() - t0, 6),
        "root_path": str(root_path),
        "command": " ".join(cmd),
        "log_file": str(run_log),
        "outputs": {
            "pr_dir": str(pr_dir),
            "sigma_pr_table_with_waivers": str(pr_table),
            "copied": copied,
        },
        "failures": [] if proc.returncode == 0 else [{"reason": "legacy_sigma_script_failed", "detail": "See build_pr_table.log"}],
    }

    return PrTableResult(
        stage,
        {
            "stage": "build_pr_table",
            "status": "not_evaluated",
            "reason": "Legacy script output parity should be validated with fixture diff in integration env.",
        },
    )


# Backward-compatible alias during rename transition.
run_get_pr_sigma = run_build_pr_table
SigmaPrResult = PrTableResult
