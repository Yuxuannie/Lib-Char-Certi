"""Common-offenders — cross-context outlier commonality (pure, stdlib only).

A "context" is one (batch_id, corner) for a given metric. This aggregates failing
arcs across contexts so systematic lib issues (a cell/arc/table-point failing in
many contexts) rank above localized ones. Three granularity keys:
  - "cell"             : the cell name (Arc parts[1])
  - "cell_arc"         : the full arc string
  - "cell_table_point" : (cell, index1, index2) slew/load grid point

Reuses outliers._failing for per-context failing rows, so the failing criterion is
identical to the rest of the outlier analysis.
"""

from __future__ import annotations

from .outliers import _failing, _cell_of, arc_indices


def _key_fields(key: str, arc: str) -> tuple:
    """Return (group_key, display_dict) for one arc under the chosen granularity."""
    cell = _cell_of(arc)
    if key == "cell_arc":
        return arc, {"cell": cell, "arc": arc, "index1": "", "index2": ""}
    if key == "cell_table_point":
        i1, i2 = arc_indices(arc)
        return (cell, i1, i2), {"cell": cell, "arc": "", "index1": i1, "index2": i2}
    return cell, {"cell": cell, "arc": "", "index1": "", "index2": ""}


def common_offenders(per_arc_by_context: dict, metric: str, key: str = "cell") -> list:
    """Aggregate failing arcs across (batch, corner) contexts.

    Args:
        per_arc_by_context: {(batch_id, corner): [per_arc_rows]}.
        metric: metric prefix (e.g. "Late_Sigma").
        key: "cell" | "cell_arc" | "cell_table_point".
    Returns one dict per offender, sorted by n_contexts desc then worst_rel_pct desc:
        {key, cell, arc, index1, index2, n_contexts, contexts, n_fail_total,
         worst_rel_pct, worst_err_ps, n_opt, n_pess, polarity}
    """
    agg: dict = {}
    for context, rows in per_arc_by_context.items():
        for r, mc, lib, ae, rel in _failing(rows, metric):
            gkey, disp = _key_fields(key, r.get("Arc", ""))
            d = agg.get(gkey)
            if d is None:
                d = {**disp, "contexts": set(), "n_fail_total": 0,
                     "worst_rel_pct": 0.0, "worst_err_ps": 0.0, "n_opt": 0, "n_pess": 0}
                agg[gkey] = d
            d["contexts"].add(context)
            d["n_fail_total"] += 1
            d["worst_rel_pct"] = max(d["worst_rel_pct"], rel)
            d["worst_err_ps"] = max(d["worst_err_ps"], ae)
            if lib < mc:
                d["n_opt"] += 1
            else:
                d["n_pess"] += 1

    out = []
    for gkey, d in agg.items():
        contexts = sorted(d["contexts"])
        polarity = ("mixed" if d["n_opt"] and d["n_pess"]
                    else "optimistic" if d["n_opt"] else "pessimistic")
        disp_key = (d["arc"] or (f"{d['cell']} [{d['index1']},{d['index2']}]"
                                 if d["index1"] else d["cell"]))
        out.append({
            "key": disp_key, "cell": d["cell"], "arc": d["arc"],
            "index1": d["index1"], "index2": d["index2"],
            "n_contexts": len(contexts), "contexts": contexts,
            "n_fail_total": d["n_fail_total"],
            "worst_rel_pct": d["worst_rel_pct"], "worst_err_ps": d["worst_err_ps"],
            "n_opt": d["n_opt"], "n_pess": d["n_pess"], "polarity": polarity,
        })
    return sorted(out, key=lambda d: (-d["n_contexts"], -d["worst_rel_pct"]))
