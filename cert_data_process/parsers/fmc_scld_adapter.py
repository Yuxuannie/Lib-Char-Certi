"""Adapter: SCLD-format parsed FMC tables -> the standard normalized FMC table.

The SCLD golden files come in two shapes, each carrying multiple timing types in
one file (filtered by the `type` column):
  - the "delay" file:  type in {delay, slew}        -> early+late sigma, meanshift, std, skew
  - the "cons"  file:  type in {hold, min_pulse_width} -> late sigma only

This module converts those rows into the exact columns the downstream lib-join
expects (same as `fmc_combine_data` / legacy `calculate.py` output), so the rest
of the pipeline is unchanged. Pure functions + stdlib csv (no pandas, no display).

Key transforms:
  - filter rows by `type`
  - map SCLD columns -> DFDS MC_* columns
  - units: ns -> ps (x1000) for nominal/sigma/meanshift/std; skewness is unscaled
  - Table_Type from type + pin direction
  - rebuild a single-token-prefix Arc that lib-join's parse_arc_info reads correctly
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Optional

DELAY_SLEW_HEADER = [
    "Arc", "Cell_Name", "output_pin", "rel_pin", "output_pin_dir", "rel_pin_dir",
    "when", "first_index", "sec_index", "MC_Nominal",
    "MC_Early_Sigma", "MC_Early_Sigma_UB", "MC_Early_Sigma_LB",
    "MC_Late_Sigma", "MC_Late_Sigma_UB", "MC_Late_Sigma_LB",
    "MC_Meansht", "MC_Meansht_UB", "MC_Meansht_LB",
    "MC_Std", "MC_Std_UB", "MC_Std_LB",
    "MC_Skew", "MC_Skew_UB", "MC_Skew_LB", "Table_Type",
]
HOLD_MPW_HEADER = [
    "Arc", "Cell_Name", "output_pin", "rel_pin", "output_pin_dir", "rel_pin_dir",
    "when", "first_index", "sec_index", "MC_Nominal",
    "MC_Late_Sigma", "MC_Late_Sigma_UB", "MC_Late_Sigma_LB", "Table_Type",
]

NS_TO_PS = 1000.0
# SCLD `type` value -> our normalized type name.
TYPE_MAP = {"delay": "delay", "slew": "slew", "hold": "hold", "min_pulse_width": "mpw"}
# Arc prefix per normalized type. Single token so lib-join's simple parse_arc_info
# (timing_type=parts[0], cell=parts[1], ...) extracts cell/pin/indices correctly.
ARC_PREFIX = {"delay": "combinational", "slew": "combinational", "hold": "hold", "mpw": "mpw"}


def _norm_key(name: str) -> str:
    """Normalize an SCLD header cell: lowercase, drop a trailing '(ns)'/'(...)' unit."""
    return re.sub(r"\(.*?\)", "", str(name)).strip().lower()


def _f(row: dict, key: str, scale: float = 1.0) -> float:
    raw = row.get(key, "")
    s = str(raw).strip()
    if not s or s.lower() in ("na", "n/a", "nan"):
        return 0.0
    try:
        return float(s) * scale
    except ValueError:
        return 0.0


def _table_type(norm_type: str, pin_dir: str) -> str:
    d = str(pin_dir).strip().lower()
    rise = d.startswith("r")
    if norm_type == "delay":
        return "cell_rise" if rise else "cell_fall"
    if norm_type == "slew":
        return "rise_transition" if rise else "fall_transition"
    return "rise_constraint" if rise else "fall_constraint"  # hold / mpw


def _as_int_str(s: str) -> str:
    try:
        return str(int(float(str(s).strip())))
    except (ValueError, TypeError):
        return str(s).strip()


def point_indices(row: dict) -> tuple[str, str]:
    """The integer table indices live in SCLD's `point` column (e.g. '3;5'),
    NOT in index_1/index_2 (which hold the slew/load VALUES). Returns 1-based-style
    index strings; lib-join applies int(float(x)-1) as it does for DFDS arcs."""
    pt = str(row.get("point", "")).strip()
    for sep in (";", ",", ":", " ", "/"):
        if sep in pt:
            parts = [p for p in pt.split(sep) if p.strip()]
            if len(parts) >= 2:
                return _as_int_str(parts[0]), _as_int_str(parts[1])
    if pt:
        return _as_int_str(pt), _as_int_str(pt)
    return "1", "1"


def _when_tokens(when: str) -> str:
    s = str(when).strip()
    if not s or s.lower() in ("none", "no_condition", "nocondition"):
        return "NO_CONDITION"
    toks = []
    for part in s.split("&"):
        p = part.strip()
        if not p:
            continue
        toks.append(("not" + p[1:]) if p.startswith("!") else p)
    return "_".join(toks) if toks else "NO_CONDITION"


def rebuild_arc(row: dict, norm_type: str) -> str:
    """Rebuild a single-token-prefix Arc parse_arc_info can read. The trailing two
    tokens are the integer table indices from SCLD's `point` column."""
    prefix = ARC_PREFIX[norm_type]
    i1, i2 = point_indices(row)
    parts = [
        prefix, row.get("cell", ""), row.get("pin", ""), row.get("pin_dir", ""),
        row.get("rel_pin", ""), row.get("rel_pin_dir", ""),
        _when_tokens(row.get("when", "")), i1, i2,
    ]
    return "_".join(str(p).strip() for p in parts)


def _common_cols(row: dict, arc: str) -> list:
    i1, i2 = point_indices(row)
    return [
        arc, row.get("cell", ""), row.get("pin", ""), row.get("rel_pin", ""),
        row.get("pin_dir", ""), row.get("rel_pin_dir", ""),
        _when_tokens(row.get("when", "")), i1, i2,
    ]


def map_delay_slew_row(row: dict, norm_type: str) -> list:
    arc = rebuild_arc(row, norm_type)
    return _common_cols(row, arc) + [
        _f(row, "nominal", NS_TO_PS),
        _f(row, "ocv_early_sigma", NS_TO_PS), _f(row, "ocv_early_sigma_ub", NS_TO_PS), _f(row, "ocv_early_sigma_lb", NS_TO_PS),
        _f(row, "ocv_late_sigma", NS_TO_PS), _f(row, "ocv_late_sigma_ub", NS_TO_PS), _f(row, "ocv_late_sigma_lb", NS_TO_PS),
        _f(row, "ocv_mean_shift", NS_TO_PS), _f(row, "ocv_mean_shift_ub", NS_TO_PS), _f(row, "ocv_mean_shift_lb", NS_TO_PS),
        _f(row, "ocv_std_dev", NS_TO_PS), _f(row, "ocv_std_dev_ub", NS_TO_PS), _f(row, "ocv_std_dev_lb", NS_TO_PS),
        _f(row, "ocv_skewness", 1.0), _f(row, "ocv_skewness_ub", 1.0), _f(row, "ocv_skewness_lb", 1.0),
        _table_type(norm_type, row.get("pin_dir", "")),
    ]


def map_hold_mpw_row(row: dict, norm_type: str) -> list:
    arc = rebuild_arc(row, norm_type)
    return _common_cols(row, arc) + [
        _f(row, "nominal", NS_TO_PS),
        _f(row, "ocv_late_sigma", NS_TO_PS), _f(row, "ocv_late_sigma_ub", NS_TO_PS), _f(row, "ocv_late_sigma_lb", NS_TO_PS),
        _table_type(norm_type, row.get("pin_dir", "")),
    ]


def _read_scld(path: Path) -> tuple[list[dict], Optional[str]]:
    """Read an SCLD CSV into normalized-key dicts. Returns (rows, error)."""
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as fh:
            reader = csv.reader(fh)
            rows = list(reader)
    except OSError as exc:
        return [], f"read_error: {exc}"
    if len(rows) < 2:
        return [], "empty_or_headerless"
    header = [_norm_key(h) for h in rows[0]]
    out = [dict(zip(header, r)) for r in rows[1:] if any(c.strip() for c in r)]
    return out, None


def adapt_scld_file(path: Path) -> tuple[dict[str, list[list]], list[str]]:
    """Split one SCLD file into {norm_type: [normalized rows]}. Returns (by_type, warnings)."""
    rows, err = _read_scld(path)
    warnings: list[str] = []
    if err:
        return {}, [f"{path.name}: {err}"]
    by_type: dict[str, list[list]] = {}
    seen_types: set = set()
    for row in rows:
        scld_type = str(row.get("type", "")).strip().lower()
        seen_types.add(scld_type)
        norm_type = TYPE_MAP.get(scld_type)
        if norm_type is None:
            continue
        if norm_type in ("delay", "slew"):
            mapped = map_delay_slew_row(row, norm_type)
        else:
            mapped = map_hold_mpw_row(row, norm_type)
        by_type.setdefault(norm_type, []).append(mapped)
    unknown = seen_types - set(TYPE_MAP)
    if unknown:
        warnings.append(f"{path.name}: ignored unknown type(s): {sorted(unknown)}")
    return by_type, warnings


def write_normalized(out_dir: Path, node: str, corner: str, norm_type: str, rows: list[list]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    header = DELAY_SLEW_HEADER if norm_type in ("delay", "slew") else HOLD_MPW_HEADER
    path = out_dir / f"fmc_result_{node}_{corner}_{norm_type}.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path
