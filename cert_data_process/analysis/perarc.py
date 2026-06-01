"""Locate and read the per-arc CSVs a batch run leaves in combined/sigma.

These back the Outliers table and the scatter drill-down. Sigma metrics
(Nominal/Early_Sigma/Late_Sigma) live in *_sigma_check_with_waivers.csv; moment
metrics (Meanshift/Std/Skew) in *_moments_check.csv. Both expose
{metric}_MC_value / {metric}_Lib_value / {metric}_Final_Status columns.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Optional

MOMENT_METRICS = {"Meanshift", "Std", "Skew"}


def metric_source(metric: str) -> str:
    return "moments" if metric in MOMENT_METRICS else "sigma"


def _f(s) -> Optional[float]:
    try:
        return float(str(s).strip())
    except (ValueError, TypeError):
        return None


def _is_pass(status: str) -> bool:
    return str(status).strip().lower() in ("pass", "passed", "true")


def find_per_arc_csv(batch_dir, corner: str, row_type: str, metric: str) -> Optional[Path]:
    """The per-arc CSV for one (corner, type, metric), or None if absent."""
    suffix = "_sigma_check_with_waivers.csv" if metric_source(metric) == "sigma" else "_moments_check.csv"
    d = Path(batch_dir) / "combined" / "sigma"
    if not d.is_dir():
        return None
    cands = [p for p in d.glob(f"*{suffix}")
             if corner in p.name and f"_{row_type}_" in p.name]
    return cands[0] if cands else None


def load_rows(csv_path) -> list:
    with Path(csv_path).open(newline="", encoding="utf-8", errors="replace") as fh:
        return list(csv.DictReader(fh))


def scatter_points(rows: list, metric: str) -> list:
    """Per-arc points for the scatter: (mc, lib, is_outlier, arc) for covered arcs."""
    mc_k, lib_k, st_k = f"{metric}_MC_value", f"{metric}_Lib_value", f"{metric}_Final_Status"
    pts = []
    for r in rows:
        mc, lib = _f(r.get(mc_k)), _f(r.get(lib_k))
        if mc is None or lib is None:
            continue
        pts.append((mc, lib, not _is_pass(r.get(st_k, "")), r.get("Arc", "")))
    return pts
