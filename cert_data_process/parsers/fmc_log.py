"""Parser for FMC fastmontecarlo.log statistical blocks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .arc_dir_name import parse_arc_info

OUTPUT_NAME_BY_TYPE = {
    "delay": "meas_delay",
    "slew": "meas_tt_out",
    "seq_delay": "cp2q",
    "hold": "cp2d",
}


def _last_float(line: str) -> float:
    return float(line.split()[-1])


def _parse_fmc_line(line: str, result: dict[str, float]) -> None:
    if "Nominal" in line:
        result["nominal"] = 1e12 * _last_float(line)
    if "Mean LB" in line:
        result["mean_lb"] = 1e12 * _last_float(line)
    if "Mean UB" in line:
        result["mean_ub"] = 1e12 * _last_float(line)
    if line.strip().startswith("Mean") and "Mean LB" not in line and "Mean UB" not in line:
        result["mean"] = 1e12 * _last_float(line)
    if "Stddev LB" in line:
        result["std_lb"] = 1e12 * _last_float(line)
    if "Stddev UB" in line:
        result["std_ub"] = 1e12 * _last_float(line)
    if line.strip().startswith("Stddev") and "Stddev LB" not in line and "Stddev UB" not in line:
        result["std"] = 1e12 * _last_float(line)
    if "Skewness LB" in line:
        result["skew_lb"] = _last_float(line)
    if "Skewness UB" in line:
        result["skew_ub"] = _last_float(line)
    if line.strip().startswith("Skewness") and "Skewness LB" not in line and "Skewness UB" not in line:
        result["skew"] = _last_float(line)
    if "Min Percentile LB" in line:
        result["min_per_lb"] = 1e12 * _last_float(line)
    if "Min Percentile UB" in line:
        result["min_per_ub"] = 1e12 * _last_float(line)
    if line.strip().startswith("Min Percentile") and "Min Percentile LB" not in line and "Min Percentile UB" not in line:
        result["min_per"] = 1e12 * _last_float(line)
    if "Max Percentile LB" in line:
        result["max_per_lb"] = 1e12 * _last_float(line)
    if "Max Percentile UB" in line:
        result["max_per_ub"] = 1e12 * _last_float(line)
    if line.strip().startswith("Max Percentile") and "Max Percentile LB" not in line and "Max Percentile UB" not in line:
        result["max_per"] = 1e12 * _last_float(line)


def parse_fastmontecarlo_log(arc_dir: Path, arc_dir_name: str, type_info: str) -> tuple[Optional[list[Any]], Optional[dict]]:
    """Parse one delay/slew fastmontecarlo.log into a legacy report row."""

    log_file_path = arc_dir / "fastmontecarlo.log"
    if not log_file_path.is_file():
        return None, {
            "arc_dir": arc_dir_name,
            "input_path": str(log_file_path),
            "reason": "missing_fastmontecarlo_log",
            "detail": "fastmontecarlo.log not found",
        }

    output_name = OUTPUT_NAME_BY_TYPE.get(type_info, "unknown")
    result: dict[str, float] = {}
    parsing = False
    section_found = False

    for line in log_file_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if f"STATISTICAL BEHAVIOR FOR MEASUREMENT {output_name}" in line:
            parsing = True
            section_found = True
            continue

        if parsing:
            _parse_fmc_line(line, result)
            if "Max Percentile UB" in line:
                parsing = False
                continue

    if not section_found:
        return None, {
            "arc_dir": arc_dir_name,
            "input_path": str(log_file_path),
            "reason": "missing_statistical_behavior_section",
            "detail": f"Expected STATISTICAL BEHAVIOR FOR MEASUREMENT {output_name}",
        }

    arc_info = parse_arc_info(arc_dir_name)
    if type_info == "delay" and arc_info.output_pin_direction == "rise":
        table_type = "cell_rise"
    elif type_info == "delay" and arc_info.output_pin_direction == "fall":
        table_type = "cell_fall"
    elif type_info == "slew" and arc_info.output_pin_direction == "rise":
        table_type = "rise_transition"
    elif type_info == "slew" and arc_info.output_pin_direction == "fall":
        table_type = "fall_transition"
    else:
        table_type = "unknown"

    mc_nominal = result.get("nominal", 0)
    mc_early_sigma_ub = (mc_nominal - result.get("min_per_ub", 0)) / 3
    mc_early_sigma_lb = (mc_nominal - result.get("min_per_lb", 0)) / 3
    mc_early_sigma = (mc_early_sigma_ub + mc_early_sigma_lb) / 2
    mc_late_sigma_ub = (result.get("max_per_ub", 0) - mc_nominal) / 3
    mc_late_sigma_lb = (result.get("max_per_lb", 0) - mc_nominal) / 3
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
        mc_nominal,
        mc_early_sigma,
        mc_early_sigma_ub,
        mc_early_sigma_lb,
        mc_late_sigma,
        mc_late_sigma_ub,
        mc_late_sigma_lb,
        result.get("mean", 0) - mc_nominal,
        result.get("mean_ub", 0) - mc_nominal,
        result.get("mean_lb", 0) - mc_nominal,
        result.get("std", 0),
        result.get("std_ub", 0),
        result.get("std_lb", 0),
        result.get("skew", 0),
        result.get("skew_ub", 0),
        result.get("skew_lb", 0),
        table_type,
    ]
    return row, None
