"""FMC Combine_data stage — parse FMC golden outputs into normalized CSVs.

Byte-identical compatibility with legacy `2-data_process/Combine_data/
calculate.py` assumes:
- Python 3.9+ runtime
- csv.writer default excel dialect (lineterminator='\r\n')
- Python str(float) numeric representation

Cross-major-version byte equivalence (e.g., Python 4.x) is not guaranteed.
"""

from __future__ import annotations

import csv
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cert_data_process.config import CertDataProcessConfig
from cert_data_process.parsers.fmc_log import parse_fastmontecarlo_log
from cert_data_process.parsers.summary_csv import parse_summary_csv

ARC_PREFIXES = ("combinational_", "edge_", "hold_", "min_pulse_width")
DELAY_SLEW_HEADER = [
    "Arc",
    "Cell_Name",
    "output_pin",
    "rel_pin",
    "output_pin_dir",
    "rel_pin_dir",
    "when",
    "first_index",
    "sec_index",
    "MC_Nominal",
    "MC_Early_Sigma",
    "MC_Early_Sigma_UB",
    "MC_Early_Sigma_LB",
    "MC_Late_Sigma",
    "MC_Late_Sigma_UB",
    "MC_Late_Sigma_LB",
    "MC_Meansht",
    "MC_Meansht_UB",
    "MC_Meansht_LB",
    "MC_Std",
    "MC_Std_UB",
    "MC_Std_LB",
    "MC_Skew",
    "MC_Skew_UB",
    "MC_Skew_LB",
    "Table_Type",
]
HOLD_MPW_HEADER = [
    "Arc",
    "Cell_Name",
    "output_pin",
    "rel_pin",
    "output_pin_dir",
    "rel_pin_dir",
    "when",
    "first_index",
    "sec_index",
    "MC_Nominal",
    "MC_Late_Sigma",
    "MC_Late_Sigma_UB",
    "MC_Late_Sigma_LB",
    "Table_Type",
]


@dataclass(frozen=True)
class FmcCombineDataResult:
    """Structured result from one FMC Combine_data stage run."""

    stage_execution: dict[str, Any]
    compatibility_stage_report: dict[str, Any]

    @property
    def failed(self) -> bool:
        return self.stage_execution["status"] == "failed"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _node(config: CertDataProcessConfig) -> str:
    return f"{config.process}_{config.process_version}"


def _corner_dir(config: CertDataProcessConfig, corner: str) -> Path:
    assert config.fmc_golden_dir is not None
    return config.fmc_golden_dir / f"{corner}_DECKS"


def _decks_dir(config: CertDataProcessConfig, corner: str, type_info: str) -> Path:
    return _corner_dir(config, corner) / type_info / "DECKS"


def _output_csv(config: CertDataProcessConfig, corner: str, type_info: str) -> Path:
    return config.output_dir / "normalized" / "fmc" / f"fmc_result_{_node(config)}_{corner}_{type_info}.csv"


def _header(type_info: str) -> list[str]:
    if type_info in ("delay", "slew"):
        return DELAY_SLEW_HEADER
    return HOLD_MPW_HEADER


def _parse_arc(arc_dir: Path, arc_dir_name: str, type_info: str) -> tuple[Optional[list[Any]], Optional[dict]]:
    if type_info in ("delay", "slew"):
        return parse_fastmontecarlo_log(arc_dir, arc_dir_name, type_info)
    return parse_summary_csv(arc_dir, arc_dir_name, type_info)


def _write_csv(path: Path, type_info: str, rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(_header(type_info))
        for row in rows:
            writer.writerow(row)


def run_fmc_combine_data(config: CertDataProcessConfig) -> FmcCombineDataResult:
    """Run FMC Combine_data for all requested corners/types."""

    started_at = _utc_now()
    started = time.monotonic()
    processed: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    log_lines = [
        "stage=fmc_combine_data",
        f"node={_node(config)}",
        f"fmc_golden_dir={config.fmc_golden_dir}",
        f"requested_corners={','.join(config.corners)}",
        f"requested_types={','.join(config.types)}",
        "",
    ]

    for corner in config.corners:
        for type_info in config.types:
            decks_dir = _decks_dir(config, corner, type_info)
            output_csv = _output_csv(config, corner, type_info)
            pair_failures: list[dict[str, Any]] = []
            rows: list[list[Any]] = []
            arc_count_total = 0

            corner_dir = _corner_dir(config, corner)
            if not corner_dir.is_dir():
                pair_failures.append(
                    {
                        "corner": corner,
                        "type": type_info,
                        "arc_dir": None,
                        "input_path": str(corner_dir),
                        "reason": "missing_corner_dir",
                        "detail": "Requested FMC corner directory does not exist",
                    }
                )
            elif not decks_dir.is_dir():
                pair_failures.append(
                    {
                        "corner": corner,
                        "type": type_info,
                        "arc_dir": None,
                        "input_path": str(decks_dir),
                        "reason": "missing_type_decks_dir",
                        "detail": "Requested FMC type DECKS directory does not exist",
                    }
                )
            else:
                arc_dirs = [name for name in os.listdir(decks_dir) if name.startswith(ARC_PREFIXES)]
                arc_count_total = len(arc_dirs)
                if not arc_dirs:
                    pair_failures.append(
                        {
                            "corner": corner,
                            "type": type_info,
                            "arc_dir": None,
                            "input_path": str(decks_dir),
                            "reason": "no_arc_dirs_found",
                            "detail": "No arc directories matched legacy FMC arc prefixes",
                        }
                    )
                for arc_dir_name in arc_dirs:
                    arc_path = decks_dir / arc_dir_name
                    row, failure = _parse_arc(arc_path, arc_dir_name, type_info)
                    if row is not None:
                        rows.append(row)
                    if failure is not None:
                        failure.update({"corner": corner, "type": type_info})
                        pair_failures.append(failure)

            if arc_count_total > 0:
                _write_csv(output_csv, type_info, rows)

            failures.extend(pair_failures)
            processed_entry = {
                "corner": corner,
                "type": type_info,
                "input_dir": str(decks_dir),
                "output_csv": str(output_csv),
                "arc_count_total": arc_count_total,
                "arc_count_processed": len(rows),
                "arc_count_failed": len(pair_failures),
            }
            processed.append(processed_entry)
            log_lines.extend(
                [
                    f"[{corner} {type_info}]",
                    f"input_dir={decks_dir}",
                    f"output_csv={output_csv}",
                    f"arc_count_total={arc_count_total}",
                    f"arc_count_processed={len(rows)}",
                    f"arc_count_failed={len(pair_failures)}",
                ]
            )
            for failure in pair_failures:
                log_lines.append(f"failure={failure}")
            log_lines.append("")

    status = "failed" if failures else "passed"
    ended_at = _utc_now()
    stage_execution = {
        "stage": "fmc_combine_data",
        "pipeline": "sigma",
        "status": status,
        "started_at_utc": started_at,
        "ended_at_utc": ended_at,
        "duration_seconds": round(time.monotonic() - started, 6),
        "requested_corners": list(config.corners),
        "requested_types": list(config.types),
        "processed": processed,
        "failures": failures,
    }
    compatibility_stage_report = {
        "stage": "fmc_combine_data",
        "status": "not_evaluated",
        "reason": "Compatibility fixture comparison runs in tests; CLI does not accept expected fixture paths in PR 2.",
    }

    log_path = config.output_dir / "logs" / "fmc_combine_data.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return FmcCombineDataResult(stage_execution, compatibility_stage_report)
