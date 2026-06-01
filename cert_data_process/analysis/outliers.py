"""Outlier breakdown for one (batch, corner, metric) — Table 2 + scatter source.

Pure: takes already-parsed per-arc rows (dicts) for a single metric prefix and
returns counts/polarity/worst-error. abs/rel errors are computed from MC/Lib
values so it works uniformly for sigma (has the columns) and moments (only has
MC/Lib values). A row is an outlier when its Final_Status is not a pass.
"""

from __future__ import annotations

from typing import Any, Optional


def _f(s) -> Optional[float]:
    try:
        return float(str(s).strip())
    except (ValueError, TypeError):
        return None


def _cell_of(arc: str) -> str:
    parts = str(arc).split("_")
    return parts[1] if len(parts) > 1 else str(arc)


def _is_pass(status: str) -> bool:
    return str(status).strip().lower() in ("pass", "passed", "true")


def outlier_breakdown(per_arc_rows: list, metric_prefix: str) -> dict:
    """Summarize the failing arcs for one metric.

    Returns: n_outlier_cells, n_outlier_arcs, polarity (optimistic/pessimistic/
    mixed/none), n_optimistic, n_pessimistic, worst_err_ps, worst_rel_pct.
    """
    mc_k = f"{metric_prefix}_MC_value"
    lib_k = f"{metric_prefix}_Lib_value"
    st_k = f"{metric_prefix}_Final_Status"

    cells: set = set()
    n_opt = n_pess = 0
    worst_abs: Optional[float] = None
    worst_rel: Optional[float] = None

    for row in per_arc_rows:
        if _is_pass(row.get(st_k, "")):
            continue
        mc, lib = _f(row.get(mc_k)), _f(row.get(lib_k))
        if mc is None or lib is None:
            continue
        cells.add(_cell_of(row.get("Arc", "")))
        if lib < mc:
            n_opt += 1
        else:
            n_pess += 1
        abs_err = abs(lib - mc)
        rel = (abs_err / abs(mc) * 100.0) if mc != 0 else 0.0
        if worst_abs is None or abs_err > worst_abs:
            worst_abs = abs_err
        if worst_rel is None or rel > worst_rel:
            worst_rel = rel

    if n_opt and n_pess:
        polarity = "mixed"
    elif n_opt:
        polarity = "optimistic"
    elif n_pess:
        polarity = "pessimistic"
    else:
        polarity = "none"

    return {
        "n_outlier_cells": len(cells),
        "n_outlier_arcs": n_opt + n_pess,
        "polarity": polarity,
        "n_optimistic": n_opt,
        "n_pessimistic": n_pess,
        "worst_err_ps": worst_abs,
        "worst_rel_pct": worst_rel,
    }
