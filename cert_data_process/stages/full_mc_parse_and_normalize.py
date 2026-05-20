"""Full MC parse + normalize stage for moments pipeline."""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cert_data_process.config import CertDataProcessConfig
from cert_data_process.parsers.arc_dir_name import parse_arc_info
from cert_data_process.parsers.full_mc_report import parse_mc_sim_params, parse_sample_moments
from cert_data_process.stages.fmc_combine_data import DELAY_SLEW_HEADER


@dataclass(frozen=True)
class FullMcNormalizeResult:
    stage_execution: dict[str, Any]
    compatibility_stage_report: dict[str, Any]

    @property
    def failed(self) -> bool:
        return self.stage_execution["status"] == "failed"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _node(config: CertDataProcessConfig) -> str:
    return f"{config.process}_{config.process_version}"


def _write_csv(path: Path, rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(DELAY_SLEW_HEADER)
        for row in rows:
            w.writerow(row)


def _type_from_arc(arc_name: str) -> str | None:
    if arc_name.startswith(("combinational_", "edge_")):
        # Full MC moments source only contains delay/slew meas columns.
        return "delay_slew"
    return None


def run_full_mc_parse_and_normalize(config: CertDataProcessConfig) -> FullMcNormalizeResult:
    started_at = _utc_now()
    t0 = time.monotonic()
    failures: list[dict[str, Any]] = []
    processed: list[dict[str, Any]] = []

    root = config.full_mc_golden_dir
    assert root is not None

    # corner and type are sourced from directory names per user lock-down.
    for corner in config.corners:
        corner_dir = root / corner
        rows_delay: list[list[Any]] = []
        rows_slew: list[list[Any]] = []

        if not corner_dir.is_dir():
            failures.append(
                {
                    "corner": corner,
                    "type": "delay,slew",
                    "arc_dir": None,
                    "input_path": str(corner_dir),
                    "reason": "missing_corner_dir",
                    "detail": "Requested Full MC corner directory does not exist",
                }
            )
            processed.append(
                {
                    "corner": corner,
                    "type": "delay,slew",
                    "input_dir": str(corner_dir),
                    "output_csv": "",
                    "arc_count_total": 0,
                    "arc_count_processed": 0,
                    "arc_count_failed": 1,
                }
            )
            continue

        arc_dirs = [p for p in corner_dir.iterdir() if p.is_dir()]
        arc_total = len(arc_dirs)
        arc_fail = 0
        arc_ok = 0

        for arc_dir in arc_dirs:
            arc_name = arc_dir.name
            if _type_from_arc(arc_name) is None:
                continue
            mc_sim = arc_dir / "mc_sim.sp"
            report = arc_dir / "OUT.ava.report"
            if not mc_sim.is_file() or not report.is_file():
                arc_fail += 1
                failures.append(
                    {
                        "corner": corner,
                        "type": "delay,slew",
                        "arc_dir": arc_name,
                        "input_path": str(arc_dir),
                        "reason": "missing_required_files",
                        "detail": "Required files mc_sim.sp and/or OUT.ava.report not found",
                    }
                )
                continue

            arc_info = parse_arc_info(arc_name)
            params = parse_mc_sim_params(mc_sim)
            moments = parse_sample_moments(report)
            if not moments or "Nominal" not in moments:
                arc_fail += 1
                failures.append(
                    {
                        "corner": corner,
                        "type": "delay,slew",
                        "arc_dir": arc_name,
                        "input_path": str(report),
                        "reason": "missing_sample_moments",
                        "detail": "Could not parse Sample_Moments section",
                    }
                )
                continue

            # Minimal moments mapping to FMC-compatible schema
            nominal_d = moments.get("Nominal", {}).get("meas_delay", 0.0) * 1e12
            nominal_s = moments.get("Nominal", {}).get("meas_tt_out", 0.0) * 1e12
            std_d = moments.get("Stddev", {}).get("meas_delay", 0.0) * 1e12
            std_s = moments.get("Stddev", {}).get("meas_tt_out", 0.0) * 1e12
            skew_d = moments.get("Skewness", {}).get("meas_delay", 0.0)
            skew_s = moments.get("Skewness", {}).get("meas_tt_out", 0.0)

            def mk_row(kind: str, nominal: float, std: float, skew: float) -> list[Any]:
                if kind == "delay":
                    table_type = "cell_rise" if arc_info.output_pin_direction == "rise" else "cell_fall"
                else:
                    table_type = "rise_transition" if arc_info.output_pin_direction == "rise" else "fall_transition"
                return [
                    arc_info.arc_name,
                    arc_info.cell_name,
                    arc_info.output_pin,
                    arc_info.rel_pin,
                    arc_info.output_pin_direction,
                    arc_info.rel_pin_direction,
                    arc_info.when,
                    arc_info.first_index,
                    arc_info.sec_index,
                    nominal,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    std,
                    0.0,
                    0.0,
                    skew,
                    0.0,
                    0.0,
                    table_type,
                ]

            rows_delay.append(mk_row("delay", nominal_d, std_d, skew_d))
            rows_slew.append(mk_row("slew", nominal_s, std_s, skew_s))

            # debug artifacts
            debug_dir = config.output_dir / "debug" / "full_mc" / arc_name
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / "netlist_params.txt").write_text(
                f"corner={corner}\narc={arc_name}\ncl={params.get('cl')}\nrel_pin_slew={params.get('rel_pin_slew')}\n",
                encoding="utf-8",
            )
            arc_ok += 1

        node = _node(config)
        delay_out = config.output_dir / "normalized" / "full_mc" / f"fmc_result_{node}_{corner}_delay.csv"
        slew_out = config.output_dir / "normalized" / "full_mc" / f"fmc_result_{node}_{corner}_slew.csv"
        if rows_delay:
            _write_csv(delay_out, rows_delay)
        if rows_slew:
            _write_csv(slew_out, rows_slew)

        processed.append(
            {
                "corner": corner,
                "type": "delay,slew",
                "input_dir": str(corner_dir),
                "output_csv": f"{delay_out},{slew_out}",
                "arc_count_total": arc_total,
                "arc_count_processed": arc_ok,
                "arc_count_failed": arc_fail,
            }
        )

    status = "failed" if failures else "passed"
    stage_execution = {
        "stage": "full_mc_parse_and_normalize",
        "pipeline": "moments",
        "status": status,
        "started_at_utc": started_at,
        "ended_at_utc": _utc_now(),
        "duration_seconds": round(time.monotonic() - t0, 6),
        "requested_corners": list(config.corners),
        "requested_types": list(config.types),
        "processed": processed,
        "failures": failures,
    }
    compatibility_stage_report = {
        "stage": "full_mc_parse_and_normalize",
        "status": "not_evaluated",
        "reason": "Full MC normalization fixture comparison will be added with user-provided expected outputs.",
    }
    return FullMcNormalizeResult(stage_execution, compatibility_stage_report)
