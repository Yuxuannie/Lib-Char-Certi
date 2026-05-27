"""FMC sigma lib-join stage (PR4 FMC-first path)."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cert_data_process.config import CertDataProcessConfig


@dataclass(frozen=True)
class SigmaLibJoinResult:
    stage_execution: dict[str, Any]
    compatibility_stage_report: dict[str, Any]

    @property
    def failed(self) -> bool:
        return self.stage_execution["status"] == "failed"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pick_mode_and_lib(glob_libs: list[Path], csv_name: str) -> tuple[str, Path | None]:
    if csv_name.endswith("_hold.csv"):
        for lf in glob_libs:
            if lf.name.endswith(".cons.lib"):
                return "Hold", lf
        return "Hold", None
    if csv_name.endswith("_delay.csv"):
        for lf in glob_libs:
            if "non_cons.lib" in lf.name:
                return "Delay", lf
        return "Delay", None
    if csv_name.endswith("_slew.csv"):
        for lf in glob_libs:
            if "non_cons.lib" in lf.name:
                return "Slew", lf
        return "Slew", None
    return "Unknown", None


def run_lib_join_sigma(config: CertDataProcessConfig) -> SigmaLibJoinResult:
    started_at = _utc_now()
    t0 = time.monotonic()

    normalized_dir = config.output_dir / "normalized" / "fmc"
    combined_dir = config.output_dir / "combined" / "sigma"
    combined_dir.mkdir(parents=True, exist_ok=True)

    script = Path("2-data_process/Combine_Lib_and_FMC/Combine_FMC_and_CDNS_lib.py")
    tcl = Path("2-data_process/Combine_Lib_and_FMC/run_ldbx.tcl")

    logs_dir = config.output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_log = logs_dir / "lib_join_sigma.log"

    if not normalized_dir.is_dir():
        stage = {
            "stage": "lib_join_sigma",
            "pipeline": "sigma",
            "status": "skipped",
            "reason": "missing_normalized_fmc_dir",
            "started_at_utc": started_at,
            "ended_at_utc": _utc_now(),
            "duration_seconds": round(time.monotonic() - t0, 6),
            "processed": [],
            "failures": [],
        }
        return SigmaLibJoinResult(stage, {"stage": "lib_join_sigma", "status": "not_evaluated", "reason": "No normalized FMC inputs."})

    csv_files = sorted(normalized_dir.glob("fmc_result_*.csv"))
    if not csv_files:
        stage = {
            "stage": "lib_join_sigma",
            "pipeline": "sigma",
            "status": "skipped",
            "reason": "no_fmc_csv_inputs",
            "started_at_utc": started_at,
            "ended_at_utc": _utc_now(),
            "duration_seconds": round(time.monotonic() - t0, 6),
            "processed": [],
            "failures": [],
        }
        return SigmaLibJoinResult(stage, {"stage": "lib_join_sigma", "status": "not_evaluated", "reason": "No normalized FMC CSV inputs."})

    lib_files = sorted(config.lib_dir.glob("*.lib"))
    processed: list[dict[str, Any]] = []

    if not lib_files:
        stage = {
            "stage": "lib_join_sigma",
            "pipeline": "sigma",
            "status": "skipped",
            "reason": "no_lib_inputs",
            "started_at_utc": started_at,
            "ended_at_utc": _utc_now(),
            "duration_seconds": round(time.monotonic() - t0, 6),
            "processed": [],
            "failures": [],
            "output_dir": str(combined_dir),
        }
        return SigmaLibJoinResult(stage, {"stage": "lib_join_sigma", "status": "not_evaluated", "reason": "No .lib files found in --lib-dir; stage skipped."})

    failures: list[dict[str, Any]] = []
    log_lines: list[str] = []

    for csv_path in csv_files:
        mode, lib_file = _pick_mode_and_lib(lib_files, csv_path.name)
        if mode == "Unknown" or lib_file is None:
            failures.append({
                "csv": str(csv_path),
                "reason": "no_matching_lib",
                "detail": f"No matching lib for mode={mode}",
            })
            continue

        cmd = [
            "liberate",
            "--trio",
            str(tcl),
            str(script),
            "-lib_path",
            str(lib_file),
            "-txt_path",
            str(csv_path),
            "-mode",
            mode,
            "-nominal_check",
        ]

        try:
            proc = subprocess.run(cmd, cwd=str(combined_dir), capture_output=True, text=True)
        except FileNotFoundError:
            stage = {
                "stage": "lib_join_sigma",
                "pipeline": "sigma",
                "status": "skipped",
                "reason": "liberate_not_found",
                "started_at_utc": started_at,
                "ended_at_utc": _utc_now(),
                "duration_seconds": round(time.monotonic() - t0, 6),
                "processed": processed,
                "failures": [],
                "log_file": str(run_log),
                "output_dir": str(combined_dir),
            }
            run_log.write_text("liberate not found in PATH; lib_join_sigma skipped\n", encoding="utf-8")
            return SigmaLibJoinResult(stage, {"stage": "lib_join_sigma", "status": "not_evaluated", "reason": "liberate executable not available in environment."})
        processed.append(
            {
                "csv": str(csv_path),
                "lib": str(lib_file),
                "mode": mode,
                "exit_code": proc.returncode,
                "cmd": " ".join(cmd),
            }
        )
        log_lines.append(f"CMD: {' '.join(cmd)}")
        log_lines.append(f"EXIT: {proc.returncode}")
        if proc.stdout:
            log_lines.append("STDOUT:")
            log_lines.append(proc.stdout)
        if proc.stderr:
            log_lines.append("STDERR:")
            log_lines.append(proc.stderr)
        log_lines.append("-" * 60)

        if proc.returncode != 0:
            failures.append(
                {
                    "csv": str(csv_path),
                    "reason": "lib_join_failed",
                    "detail": f"liberate exited with {proc.returncode}",
                }
            )

    run_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    status = "failed" if failures else "passed"
    if processed and len(failures) < len(processed):
        # preserve progress visibility; still fail for strict pipeline semantics.
        status = "failed" if failures else "passed"

    stage = {
        "stage": "lib_join_sigma",
        "pipeline": "sigma",
        "status": status,
        "started_at_utc": started_at,
        "ended_at_utc": _utc_now(),
        "duration_seconds": round(time.monotonic() - t0, 6),
        "processed": processed,
        "failures": failures,
        "log_file": str(run_log),
        "output_dir": str(combined_dir),
    }
    return SigmaLibJoinResult(
        stage,
        {
            "stage": "lib_join_sigma",
            "status": "not_evaluated",
            "reason": "Legacy lib-join output parity should be validated by RPT diff against legacy flow.",
        },
    )
