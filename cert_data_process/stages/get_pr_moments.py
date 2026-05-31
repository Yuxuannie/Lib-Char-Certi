"""Moments PR stage — moments (meanshift/std/skew) pass-rate from FMC data only.

G4: Full MC is removed. Moments are computed from the same FMC combine RPT used
by the sigma stage (`combined/sigma/*_fmc_cdns_lib_comp.rpt`), via
`2-data_process/get_PR/Moments/check_moments_from_fmc.py`. Outputs land in
`pr/moments/` alongside a terminal print, mirroring the sigma PR stage.
"""

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
class MomentsPrResult:
    stage_execution: dict[str, Any]
    compatibility_stage_report: dict[str, Any]

    @property
    def failed(self) -> bool:
        return self.stage_execution["status"] == "failed"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_get_pr_moments(config: CertDataProcessConfig) -> MomentsPrResult:
    started_at = _utc_now()
    t0 = time.monotonic()

    output_dir = config.output_dir.resolve()
    root_path = (output_dir / "combined" / "sigma").resolve()  # FMC RPTs live here
    pr_dir = (output_dir / "pr" / "moments").resolve()
    pr_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "2-data_process/get_PR/Moments/check_moments_from_fmc.py").resolve()

    moments_types = [t for t in config.types if t in {"delay", "slew"}]
    logs_dir = (output_dir / "logs").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_log = logs_dir / "get_pr_moments.log"

    def _stage(status, **extra):
        s = {
            "stage": "get_pr_moments",
            "pipeline": "moments",
            "status": status,
            "started_at_utc": started_at,
            "ended_at_utc": _utc_now(),
            "duration_seconds": round(time.monotonic() - t0, 6),
            "root_path": str(root_path),
        }
        s.update(extra)
        return s

    if not moments_types:
        stage = _stage("skipped", reason="no_delay_slew_types")
        run_log.write_text("stage=get_pr_moments\nresult=skipped reason=no_delay_slew_types\n", encoding="utf-8")
        return MomentsPrResult(stage, {"stage": "get_pr_moments", "status": "not_evaluated", "reason": "Moments need delay/slew."})

    if not script.is_file():
        stage = _stage("failed", reason="missing_moments_script", failures=[{"reason": "missing_moments_script", "detail": str(script)}])
        run_log.write_text(f"stage=get_pr_moments\nresult=failed reason=missing_moments_script script={script}\n", encoding="utf-8")
        return MomentsPrResult(stage, {"stage": "get_pr_moments", "status": "not_evaluated", "reason": "Moments script missing."})

    if not root_path.is_dir():
        stage = _stage("skipped", reason="missing_sigma_combined_dir")
        run_log.write_text("stage=get_pr_moments\nresult=skipped reason=missing_sigma_combined_dir\n", encoding="utf-8")
        return MomentsPrResult(stage, {"stage": "get_pr_moments", "status": "not_evaluated", "reason": "No FMC RPT inputs."})

    rpt_candidates = [f for f in root_path.iterdir() if f.is_file() and f.suffix == ".rpt" and "fmc" in f.name.lower()]
    if not rpt_candidates:
        stage = _stage("skipped", reason="no_fmc_rpt_inputs")
        run_log.write_text("stage=get_pr_moments\nresult=skipped reason=no_fmc_rpt_inputs\n", encoding="utf-8")
        return MomentsPrResult(stage, {"stage": "get_pr_moments", "status": "not_evaluated", "reason": "No FMC RPT files found."})

    cmd = [
        "python3", str(script),
        "--root_path", str(root_path),
        "--corners", *list(config.corners),
        "--types", *moments_types,
        "--log_level", "INFO",
    ]
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)

    deliverables = ["moments_PR_table.csv", "moments_summary_table.txt"]
    copied = []
    for name in deliverables:
        src = root_path / name
        if src.is_file():
            dst = pr_dir / name
            shutil.copy2(src, dst)
            copied.append(str(dst))

    log_lines = [
        "stage=get_pr_moments",
        f"started_at_utc={started_at}",
        f"script={script}",
        f"requested_types={','.join(moments_types)}",
        f"cmd={' '.join(cmd)}",
        f"exit_code={proc.returncode}",
        "",
        "STDOUT", proc.stdout, "",
        "STDERR", proc.stderr, "",
        "pr_moments_outputs:",
        *[f"  {c}" for c in copied],
        f"result={'passed' if proc.returncode == 0 else 'failed'}",
    ]
    run_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    pr_table = pr_dir / "moments_PR_table.csv"
    print(f"[get_pr_moments] PR outputs copied to: {pr_dir}")
    if pr_table.is_file():
        print("[get_pr_moments] moments_PR_table.csv:")
        for line in pr_table.read_text(encoding="utf-8").splitlines():
            print(f"    {line}")
    else:
        print("[get_pr_moments] WARNING: moments_PR_table.csv not produced (see get_pr_moments.log)")

    stage = _stage(
        "passed" if proc.returncode == 0 else "failed",
        command=" ".join(cmd),
        log_file=str(run_log),
        outputs={"pr_dir": str(pr_dir), "moments_pr_table": str(pr_table), "copied": copied},
        failures=[] if proc.returncode == 0 else [{"reason": "moments_script_failed", "detail": "See get_pr_moments.log"}],
    )
    return MomentsPrResult(stage, {"stage": "get_pr_moments", "status": "not_evaluated", "reason": "Moments PR validated by user against reference."})
