"""Outlier breakdown + rankings for one (batch, corner, metric) — Table 2 + scatter source.

Pure: takes already-parsed per-arc rows (dicts) for a single metric prefix and
returns counts/polarity/worst-error. abs/rel errors are computed from MC/Lib
values so it works uniformly for sigma (has the columns) and moments (only has
MC/Lib values). A row is an outlier when its Final_Status is not a pass.
"""

from __future__ import annotations

import re as _re
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
        rel = rel_pct_for(row, metric_prefix, mc, lib)
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


def arc_indices(arc: str):
    """Return (index1, index2) integer strings from the trailing tokens of an arc name.
    Returns ('', '') when the arc name doesn't match the expected format."""
    parts = str(arc).split("_")
    if len(parts) >= 2 and _re.fullmatch(r"-?\d+", parts[-1] or ""):
        return (parts[-2], parts[-1])
    return ("", "")


def rel_pct_for(row, metric, mc, lib) -> float:
    """Relative error % using the ENGINE's denominator.

    The engine (check_sigma) computes rel_err = (Lib-MC) / max(|Nominal|, |MC|) and
    persists it as ``{metric}_rel_err`` (a signed fraction). We read that so the
    displayed rel% matches the pass/fail thresholds per type (delay/slew sigma are
    divided by the large nominal, NOT the small sigma). Fallback to |Lib-MC|/|MC|
    only when the column is absent (older / moments CSVs)."""
    raw = row.get(f"{metric}_rel_err")
    v = _f(raw)
    if v is not None and str(raw).strip() != "":
        return abs(v) * 100.0
    return abs(lib - mc) / abs(mc) * 100.0 if mc != 0 else 0.0


def _polarity_ok(mc, lib, polarity: str) -> bool:
    if polarity == "opt":
        return lib < mc
    if polarity == "pess":
        return lib >= mc
    return True


def _failing(rows, metric, polarity: str = "all"):
    """Yield (row, mc, lib, abs_err, rel_pct) for failing covered arcs.

    rel_pct uses the engine denominator (see rel_pct_for). ``polarity`` filters to
    'opt' (Lib<MC), 'pess' (Lib>=MC), or 'all'."""
    mc_k, lib_k, st_k = f"{metric}_MC_value", f"{metric}_Lib_value", f"{metric}_Final_Status"
    for r in rows:
        if _is_pass(r.get(st_k, "")):
            continue
        mc, lib = _f(r.get(mc_k)), _f(r.get(lib_k))
        if mc is None or lib is None:
            continue
        if not _polarity_ok(mc, lib, polarity):
            continue
        yield r, mc, lib, abs(lib - mc), rel_pct_for(r, metric, mc, lib)


def rank_by_cell(rows, metric, polarity: str = "all"):
    """One dict per failing cell, sorted by n_fail desc then worst_rel_pct desc."""
    agg: dict = {}
    for r, mc, lib, ae, rel in _failing(rows, metric, polarity):
        c = _cell_of(r.get("Arc", ""))
        d = agg.setdefault(c, {"cell": c, "n_fail": 0, "worst_rel_pct": 0.0,
                               "worst_err_ps": 0.0, "n_opt": 0, "n_pess": 0})
        d["n_fail"] += 1
        d["worst_rel_pct"] = max(d["worst_rel_pct"], rel)
        d["worst_err_ps"] = max(d["worst_err_ps"], ae)
        if lib < mc:
            d["n_opt"] += 1
        else:
            d["n_pess"] += 1
    for d in agg.values():
        d["polarity"] = ("mixed" if d["n_opt"] and d["n_pess"]
                         else "optimistic" if d["n_opt"] else "pessimistic")
    return sorted(agg.values(), key=lambda d: (-d["n_fail"], -d["worst_rel_pct"]))


def rank_by_table_point(rows, metric, polarity: str = "all"):
    """One dict per (index1, index2) grid point with failing arcs."""
    agg: dict = {}
    for r, mc, lib, ae, rel in _failing(rows, metric, polarity):
        i1, i2 = arc_indices(r.get("Arc", ""))
        d = agg.setdefault((i1, i2), {"index1": i1, "index2": i2, "n_fail": 0,
                                       "worst_rel_pct": 0.0, "worst_err_ps": 0.0})
        d["n_fail"] += 1
        d["worst_rel_pct"] = max(d["worst_rel_pct"], rel)
        d["worst_err_ps"] = max(d["worst_err_ps"], ae)
    return sorted(agg.values(), key=lambda d: (-d["n_fail"], -d["worst_rel_pct"]))


def worst_arcs(rows, metric, top: int = 20, polarity: str = "all"):
    """Top-N failing arcs sorted by rel_pct desc."""
    out = []
    for r, mc, lib, ae, rel in _failing(rows, metric, polarity):
        i1, i2 = arc_indices(r.get("Arc", ""))
        out.append({"arc": r.get("Arc", ""), "cell": _cell_of(r.get("Arc", "")),
                    "index1": i1, "index2": i2, "mc": mc, "lib": lib,
                    "abs_err_ps": ae, "rel_pct": rel,
                    "direction": "optimistic" if lib < mc else "pessimistic"})
    return sorted(out, key=lambda d: -d["rel_pct"])[:top]
