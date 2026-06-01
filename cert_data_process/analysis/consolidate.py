"""Consolidate N batch run-records into the Table-1 PR pivot.

Pure functions (stdlib only). Rows are the slide's data-types; columns are each
run's (batch_id, VT, base/mb, corner). Cells carry the PR (default basis = Waiver1)
and a color band (green>=95, amber 90-95, red<90).
"""

from __future__ import annotations

from typing import Any, Optional

# (label, class, source_type, metric_key) — order matches the target slide.
PR_ROWS = [
    {"label": "hold", "cls": "cons", "type": "hold", "metric": "Nominal"},
    {"label": "ocv_const_hold", "cls": "cons", "type": "hold", "metric": "Late_Sigma"},
    {"label": "delay", "cls": "non_cons", "type": "delay", "metric": "Nominal"},
    {"label": "ocv_delay_early", "cls": "non_cons", "type": "delay", "metric": "Early_Sigma"},
    {"label": "ocv_delay_late", "cls": "non_cons", "type": "delay", "metric": "Late_Sigma"},
    {"label": "delay_mns", "cls": "non_cons", "type": "delay", "metric": "Meanshift"},
    {"label": "delay_skn", "cls": "non_cons", "type": "delay", "metric": "Skew"},
    {"label": "delay_std", "cls": "non_cons", "type": "delay", "metric": "Std"},
    {"label": "trans", "cls": "non_cons", "type": "slew", "metric": "Nominal"},
    {"label": "ocv_trans_early", "cls": "non_cons", "type": "slew", "metric": "Early_Sigma"},
    {"label": "ocv_trans_late", "cls": "non_cons", "type": "slew", "metric": "Late_Sigma"},
    {"label": "trans_mns", "cls": "non_cons", "type": "slew", "metric": "Meanshift"},
    {"label": "trans_skn", "cls": "non_cons", "type": "slew", "metric": "Skew"},
    {"label": "trans_std", "cls": "non_cons", "type": "slew", "metric": "Std"},
]

# metric -> (source, base_field, w1_field) in the run-record rows.
_SIGMA = {"Nominal": ("sigma", "nomBase", "nomW1"),
          "Early_Sigma": ("sigma", "eBase", "eW1"),
          "Late_Sigma": ("sigma", "lBase", "lW1")}
_MOM = {"Meanshift": ("moments", "ms", "msW1"),
        "Std": ("moments", "std", "stdW1"),
        "Skew": ("moments", "skew", "skewW1")}
_METRIC_SRC = {**_SIGMA, **_MOM}

GREEN_LOW = 95.0
AMBER_LOW = 90.0


def pr_color(pr: Optional[float], green_low: float = GREEN_LOW, amber_low: float = AMBER_LOW) -> str:
    if pr is None:
        return "none"
    if pr >= green_low:
        return "green"
    if pr >= amber_low:
        return "amber"
    return "red"


def _value(metric: str, basis: str, sig: Optional[dict], mom: Optional[dict]) -> Optional[float]:
    src, base_f, w1_f = _METRIC_SRC[metric]
    row = sig if src == "sigma" else mom
    if not row:
        return None
    return row.get(w1_f if basis == "w1" else base_f)


def consolidate_pr(records: list, basis: str = "w1",
                   green_low: float = GREEN_LOW, amber_low: float = AMBER_LOW) -> dict:
    """Build the pivot: ordered columns (one per batch x corner) and a cell map.

    cells[(row_label, col_index)] = {"pr": float|None, "color": str, "health": str}
    """
    columns: list = []
    sig_idx: dict = {}
    mom_idx: dict = {}

    for rec in records:
        cfg = rec.get("config", {})
        batch_id = rec.get("batch_id") or rec.get("name", "?")
        vt = cfg.get("vt_type", "")
        libtype = cfg.get("library_type", "auto")
        corners: list = []
        for s in rec.get("sigma", []):
            if s["corner"] not in corners:
                corners.append(s["corner"])
        for m in rec.get("moments", []):
            if m["corner"] not in corners:
                corners.append(m["corner"])
        sig_by = {(s["corner"], s["type"]): s for s in rec.get("sigma", [])}
        mom_by = {(m["corner"], m["type"]): m for m in rec.get("moments", [])}
        for corner in corners:
            ci = len(columns)
            columns.append({"batch_id": batch_id, "vt": vt, "libtype": libtype, "corner": corner})
            sig_idx[ci] = sig_by
            mom_idx[ci] = mom_by

    cells: dict = {}
    for ci in range(len(columns)):
        corner = columns[ci]["corner"]
        for row in PR_ROWS:
            sig = sig_idx[ci].get((corner, row["type"]))
            mom = mom_idx[ci].get((corner, row["type"]))
            pr = _value(row["metric"], basis, sig, mom)
            health = (sig or mom or {}).get("health", "UNKNOWN")
            cells[(row["label"], ci)] = {
                "pr": pr, "color": pr_color(pr, green_low, amber_low), "health": health,
            }
    return {"columns": columns, "rows": PR_ROWS, "cells": cells, "basis": basis}
