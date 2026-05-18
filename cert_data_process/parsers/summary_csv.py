"""Parser for hold/mpw summary CSV files from FMC decks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from .arc_dir_name import parse_arc_info


def _summary_number(path: Path) -> int:
    match = re.search(r"\d+", path.name)
    if not match:
        return -1
    return int(match.group())


def parse_summary_csv(arc_dir: Path, arc_dir_name: str, type_info: str) -> tuple[Optional[list[Any]], Optional[dict]]:
    """Parse one hold/mpw arc summary CSV into a legacy report row."""

    csv_files = [path for path in arc_dir.iterdir() if path.name.startswith("summary") and path.name.endswith(".csv")]
    if not csv_files:
        return None, {
            "arc_dir": arc_dir_name,
            "input_path": str(arc_dir),
            "reason": "missing_summary_csv",
            "detail": "No summary*.csv files found",
        }

    csv_file_path = max(csv_files, key=_summary_number)
    try:
        lines = csv_file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return None, {
            "arc_dir": arc_dir_name,
            "input_path": str(csv_file_path),
            "reason": "summary_csv_read_error",
            "detail": str(exc),
        }

    if len(lines) < 2:
        return None, {
            "arc_dir": arc_dir_name,
            "input_path": str(csv_file_path),
            "reason": "summary_csv_missing_data_row",
            "detail": "summary CSV must contain a header and one data row",
        }

    header = lines[0].strip().split(",")
    try:
        nominal_index = header.index("Nominal")
        percentile_lb_index = header.index("Percentile LB")
        percentile_ub_index = header.index("Percentile UB")
    except ValueError as exc:
        return None, {
            "arc_dir": arc_dir_name,
            "input_path": str(csv_file_path),
            "reason": "summary_csv_missing_required_column",
            "detail": str(exc),
        }

    try:
        data_line = lines[1].strip().split(",")
        nominal = float(data_line[nominal_index]) * 1e12
        percentile_lb = float(data_line[percentile_lb_index]) * 1e12
        percentile_ub = float(data_line[percentile_ub_index]) * 1e12
    except (IndexError, ValueError) as exc:
        return None, {
            "arc_dir": arc_dir_name,
            "input_path": str(csv_file_path),
            "reason": "summary_csv_malformed_data_row",
            "detail": str(exc),
        }

    arc_info = parse_arc_info(arc_dir_name)
    if arc_info.output_pin_direction == "rise":
        table_type = "rise_constraint"
    elif arc_info.output_pin_direction == "fall":
        table_type = "fall_constraint"
    else:
        table_type = "unknown"

    mc_late_sigma_ub = (percentile_ub - nominal) / 3
    mc_late_sigma_lb = (percentile_lb - nominal) / 3
    mc_late_sigma = (mc_late_sigma_ub + mc_late_sigma_lb) / 2

    row = [
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
        mc_late_sigma,
        mc_late_sigma_ub,
        mc_late_sigma_lb,
        table_type,
    ]
    return row, None
