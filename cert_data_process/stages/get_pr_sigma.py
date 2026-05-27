"""PR table stage wrapper using legacy check_sigma.py."""

from __future__ import annotations

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

    root_path = config.output_dir / "combined" / "sigma"
    script = Path("2-data_process/get_PR/Sigma/check_sigma.py")
    cmd = [
        "python3",
        str(script),
        "--root_path",
        str(root_path),
        "--corners",
        *list(config.corners),
        "--types",
        *[t for t in config.types if t in {"delay", "slew", "hold"}],
        "--log_level",
        "INFO",
    ]

    logs_dir = config.output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_log = logs_dir / "build_pr_table.log"

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
        return PrTableResult(stage, {"stage": "build_pr_table", "status": "not_evaluated", "reason": "No sigma RPT files found; stage skipped."})
    proc = subprocess.run(cmd, capture_output=True, text=True)
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
    run_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

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
            "sigma_pr_table": str(root_path / "sigma_PR_table.csv"),
            "sigma_pr_table_moments": str(root_path / "sigma_PR_table_moments.csv"),
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
