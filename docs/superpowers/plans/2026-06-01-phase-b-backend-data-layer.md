# Phase B — Backend Data Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the decision-free backend that the consolidated PR pivot (Table 1) and outlier breakdown (Table 2) views will consume — add per-type Nominal pass-rate, a multi-batch pivot builder, and an outlier-metrics function — all as pure, unit-tested functions with no UI.

**Architecture:** Nominal PR is added to the existing `check_sigma_with_waivers.py` (the RPT already carries `MC_Nominal`/`CDNS_Lib_Nominal`; only rel-error applies since Nominal has no CI bounds). Two new pure modules under `cert_data_process/analysis/` turn run-records + per-arc CSVs into the pivot model and the outlier breakdown. The desktop views (Phases C–F) sit on top of these in later plans.

**Tech Stack:** Python 3.9+, stdlib `csv` for the new modules (no pandas in the new package), `pytest`, `@dataclass`. The legacy check script keeps using pandas.

**Approved defaults (spec §6):** thresholds green≥95 / amber 90–95 / red<90; basis = PR_with_Waiver1; Nominal criterion mirrors sigma (rel 3% delay/hold, 6% slew, CI n/a); outlier breakdown for cells below 95; self-populate from our per-arc data.

---

## File structure

- **Modify** `2-data_process/get_PR/Sigma/check_sigma_with_waivers.py` — add `Nominal` as a checked param (rel-only), emit `Nominal_Base_PR` / `Nominal_PR_with_Waiver1` columns.
- **Modify** `cert_data_process/web/summary.py` — `build_sigma_rows` reads the new Nominal columns into each sigma row (`nomBase`/`nomW1`).
- **Create** `cert_data_process/analysis/__init__.py`
- **Create** `cert_data_process/analysis/consolidate.py` — `PR_ROWS`, `pr_color`, `consolidate_pr(records, basis, thresholds)`.
- **Create** `cert_data_process/analysis/outliers.py` — `outlier_breakdown(per_arc_rows, metric_prefix, basis)`.
- **Create** `tests/test_nominal_pr.py`, `tests/test_consolidate.py`, `tests/test_outliers.py`.

---

## Task 1: Make CI-bounds optional in `check_pass_with_waivers` (enables rel-only Nominal)

**Files:**
- Modify: `2-data_process/get_PR/Sigma/check_sigma_with_waivers.py` (the CI section ~lines 205–224 and the NaN guard ~line 155)
- Test: `tests/test_nominal_pr.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_nominal_pr.py
import importlib.util, pathlib
import pandas as pd

_SPEC = importlib.util.spec_from_file_location(
    "check_sigma_ww",
    pathlib.Path("2-data_process/get_PR/Sigma/check_sigma_with_waivers.py"),
)
# NOTE: the module has no __main__ guard around main(), but importing it only
# defines functions (main() runs under `if __name__ == "__main__"`). Verify that
# guard exists in Step 3; if not, this import executes main() — see Step 3 note.
csm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(csm)


def test_nominal_pass_uses_rel_error_only_when_no_ci_columns():
    # Nominal row: lib within 1% of mc, no MC_Nominal_LB/UB present.
    row = pd.Series({"MC_Nominal": 100.0, "CDNS_Lib_Nominal": 100.5})
    r = csm.check_pass_with_waivers(row, "delay", "Nominal", lib_prefix="CDNS_Lib")
    assert r["covered"] is True
    assert r["base_pass"] is True           # 0.5% <= 3% delay threshold
    assert r["waiver1_ci_enlarged"] is True # no CI -> waiver1 falls back to rel pass


def test_nominal_fail_when_rel_error_exceeds_threshold():
    row = pd.Series({"MC_Nominal": 100.0, "CDNS_Lib_Nominal": 110.0})  # 10% off
    r = csm.check_pass_with_waivers(row, "delay", "Nominal", lib_prefix="CDNS_Lib")
    assert r["covered"] is True
    assert r["base_pass"] is False
    assert r["waiver1_ci_enlarged"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/nieyuxuan/Downloads/Work/Lib-Char-Certi && PYTHONPATH=. python -m pytest tests/test_nominal_pr.py -v`
Expected: FAIL — `KeyError: 'MC_Nominal_LB'` (CI columns required).

- [ ] **Step 3: Make CI optional in `check_pass_with_waivers`**

First confirm the module has `if __name__ == "__main__": main()` (it does — bottom of file), so importing is safe.

In `check_pass_with_waivers`, replace the hard CI-bound reads with `.get`-style optional handling. Find the block that currently reads (around lines 205–224):

```python
        ci_lb = row[f"{mc_prefix}_{param_name}_LB"]
        ci_ub = row[f"{mc_prefix}_{param_name}_UB"]
        ci_bounds_pass = (ci_lb <= lib_value <= ci_ub)
```

Replace with:

```python
        # CI bounds are optional: Nominal has no MC_*_LB/UB columns, so it is a
        # rel-error-only check and Waiver1 (CI enlargement) collapses to the base pass.
        lb_key, ub_key = f"{mc_prefix}_{param_name}_LB", f"{mc_prefix}_{param_name}_UB"
        has_ci = (lb_key in row.index) and (ub_key in row.index) \
            and not pd.isna(row[lb_key]) and not pd.isna(row[ub_key])
        if has_ci:
            ci_lb = float(row[lb_key]); ci_ub = float(row[ub_key])
            ci_bounds_pass = (ci_lb <= lib_value <= ci_ub)
        else:
            ci_lb = ci_ub = None
            ci_bounds_pass = False
```

Then find the Waiver1 enlargement block (around lines 218–224):

```python
        enlarged_lb = ci_lb - 0.06 * abs(ci_lb)
        enlarged_ub = ci_ub + 0.06 * abs(ci_ub)
        waiver1_ci_enlarged = (enlarged_lb <= lib_value <= enlarged_ub)
```

Replace with:

```python
        if has_ci:
            enlarged_lb = ci_lb - 0.06 * abs(ci_lb)
            enlarged_ub = ci_ub + 0.06 * abs(ci_ub)
            waiver1_ci_enlarged = (enlarged_lb <= lib_value <= enlarged_ub)
        else:
            # No CI -> the only waiver path is the rel-error base pass itself.
            waiver1_ci_enlarged = bool(rel_pass)
```

(`rel_pass` is already computed just above these lines; `pd` is already imported.)

- [ ] **Step 4: Add the Nominal rel-error threshold**

Find the threshold ladder (around lines 178–200, `if type_name == 'delay':` ...). Add a Nominal branch at the TOP of the per-type blocks. For delay:

```python
    if type_name == 'delay':
        if param_name == 'Nominal':
            rel_threshold = 0.03          # nominal mirrors sigma 3%
        elif param_name in ['Early_Sigma', 'Late_Sigma']:
            rel_threshold = 0.03
        ...
```

For slew:

```python
    elif type_name == 'slew':
        if param_name == 'Nominal':
            rel_threshold = 0.06          # nominal mirrors slew sigma 6%
        elif param_name in ['Early_Sigma', 'Late_Sigma']:
            rel_threshold = 0.06
        ...
```

For hold (the `else:` branch — already a flat `rel_threshold = 0.03`), leave as-is (covers Nominal too, 3%).

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_nominal_pr.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add 2-data_process/get_PR/Sigma/check_sigma_with_waivers.py tests/test_nominal_pr.py
git commit -m "feat: make CI bounds optional in waiver check to support rel-only Nominal PR"
```

---

## Task 2: Compute & emit Nominal PR in the sigma table

**Files:**
- Modify: `2-data_process/get_PR/Sigma/check_sigma_with_waivers.py` (`process_sigma_file_with_waivers` param list + required columns; `generate_waiver_summary_table` columns)
- Test: `tests/test_nominal_pr.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
def test_sigma_params_include_nominal_and_skip_ci_requirement(monkeypatch):
    # delay/slew should check Nominal + Early + Late; hold should check Nominal + Late.
    assert csm._sigma_params_for("delay") == ["Nominal", "Early_Sigma", "Late_Sigma"]
    assert csm._sigma_params_for("hold") == ["Nominal", "Late_Sigma"]

def test_required_columns_for_nominal_have_no_ci():
    cols = csm._required_columns_for(["Nominal", "Late_Sigma"], "CDNS_Lib")
    assert "MC_Nominal" in cols and "CDNS_Lib_Nominal" in cols
    assert "MC_Nominal_LB" not in cols              # nominal has no CI
    assert "MC_Late_Sigma_LB" in cols               # sigma still needs CI
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_nominal_pr.py -v -k "sigma_params or required_columns"`
Expected: FAIL — `AttributeError: module has no attribute '_sigma_params_for'`.

- [ ] **Step 3: Extract the two helpers and use them**

Add near the top of `process_sigma_file_with_waivers` scope (module level, after `find_rpt_files`):

```python
def _sigma_params_for(type_name):
    """Params checked for a type, Nominal first (it maps to the slide's delay/trans/hold rows)."""
    if type_name in ('delay', 'slew'):
        return ['Nominal', 'Early_Sigma', 'Late_Sigma']
    return ['Nominal', 'Late_Sigma']  # hold

def _required_columns_for(params, vendor_prefix):
    """Required RPT columns; Nominal has no CI bounds (MC_*_LB/UB) so they're omitted."""
    cols = ['Arc']
    for p in params:
        cols += [f'MC_{p}', f'{vendor_prefix}_{p}']
        if p != 'Nominal':
            cols += [f'MC_{p}_LB', f'MC_{p}_UB']
    return cols
```

In `process_sigma_file_with_waivers`, replace the existing param selection (around lines 329–338):

```python
        if type_name in ['delay', 'slew']:
            sigma_params = ['Early_Sigma', 'Late_Sigma']
        else:  # hold
            sigma_params = ['Late_Sigma']

        for param in sigma_params:
            required_columns.extend([...])
        missing_columns = [col for col in required_columns if col not in df.columns]
```

with:

```python
        sigma_params = _sigma_params_for(type_name)
        required_columns = _required_columns_for(sigma_params, vendor_prefix)
        missing_columns = [col for col in required_columns if col not in df.columns]
```

(Delete the now-duplicated `required_columns = ['Arc']` init above it.)

- [ ] **Step 4: Add Nominal to the summary table columns**

In `generate_waiver_summary_table`, the delay/slew dataframes currently list Early+Late columns. Add Nominal as the FIRST PR pair for delay/slew/hold. Change the param selection inside the fill loop (around line 628):

```python
            params = ['Early_Sigma', 'Late_Sigma'] if type_name in ('delay', 'slew') else ['Late_Sigma']
```

to:

```python
            params = _sigma_params_for(type_name)
```

And add the columns to each dataframe definition (around lines 556–565), prepending `'Nominal_Base_PR', 'Nominal_PR_with_Waiver1'` after `'Corner'`:

```python
    delay_df = pd.DataFrame(columns=[
        'Corner', 'Nominal_Base_PR', 'Nominal_PR_with_Waiver1',
        'Early_Sigma_Base_PR', 'Early_Sigma_PR_with_Waiver1',
        'Late_Sigma_Base_PR', 'Late_Sigma_PR_with_Waiver1'] + cov_cols)
    slew_df = pd.DataFrame(columns=[
        'Corner', 'Nominal_Base_PR', 'Nominal_PR_with_Waiver1',
        'Early_Sigma_Base_PR', 'Early_Sigma_PR_with_Waiver1',
        'Late_Sigma_Base_PR', 'Late_Sigma_PR_with_Waiver1'] + cov_cols)
    hold_df = pd.DataFrame(columns=[
        'Corner', 'Nominal_Base_PR', 'Nominal_PR_with_Waiver1',
        'Late_Sigma_Base_PR', 'Late_Sigma_PR_with_Waiver1'] + cov_cols)
    mpw_df = pd.DataFrame(columns=[
        'Corner', 'Nominal_Base_PR', 'Nominal_PR_with_Waiver1',
        'Late_Sigma_Base_PR', 'Late_Sigma_PR_with_Waiver1'] + cov_cols)
```

The existing fill loop already writes `f'{param}_Base_PR'` / `f'{param}_PR_with_Waiver1'` for each param in `params`, so Nominal is populated automatically.

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest tests/test_nominal_pr.py -v`
Expected: PASS (all 4 tests).

- [ ] **Step 6: Commit**

```bash
git add 2-data_process/get_PR/Sigma/check_sigma_with_waivers.py tests/test_nominal_pr.py
git commit -m "feat: compute and emit per-type Nominal PR in sigma table"
```

---

## Task 3: Read Nominal into the run-record sigma rows

**Files:**
- Modify: `cert_data_process/web/summary.py` (`build_sigma_rows`)
- Test: `tests/test_results_view.py` (extend) or `tests/test_consolidate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_consolidate.py (new file; import target added in Task 4)
import csv
from cert_data_process.web.summary import build_sigma_rows

def test_build_sigma_rows_reads_nominal(tmp_path):
    d = tmp_path / "pr" / "sigma"; d.mkdir(parents=True)
    f = d / "sigma_PR_table_with_waivers.csv"
    with f.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Corner", "Nominal_Base_PR", "Nominal_PR_with_Waiver1",
                    "Early_Sigma_Base_PR", "Early_Sigma_PR_with_Waiver1",
                    "Late_Sigma_Base_PR", "Late_Sigma_PR_with_Waiver1",
                    "Total_Arcs", "Covered", "Uncovered", "Coverage", "Data_Health", "Type"])
        w.writerow(["c1", "100.0%", "100.0%", "99.5%", "99.6%", "92.6%", "92.7%",
                    "1180", "1180", "0", "100.0%", "OK", "delay"])
    rows = build_sigma_rows(tmp_path)
    assert rows[0]["nomBase"] == 100.0 and rows[0]["nomW1"] == 100.0
    assert rows[0]["lBase"] == 92.6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_consolidate.py::test_build_sigma_rows_reads_nominal -v`
Expected: FAIL — `KeyError: 'nomBase'`.

- [ ] **Step 3: Add nominal fields to `build_sigma_rows`**

In `cert_data_process/web/summary.py`, inside `build_sigma_rows`, add to the `row` dict:

```python
            "nomBase": _num(d.get("Nominal_Base_PR")),
            "nomW1": _num(d.get("Nominal_PR_with_Waiver1")),
```

(Place them right after `"type": d.get("Type", ""),`. `_num` already returns `None` for missing/`"N/A"`, so older tables without Nominal columns stay backward-compatible.)

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_consolidate.py::test_build_sigma_rows_reads_nominal -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cert_data_process/web/summary.py tests/test_consolidate.py
git commit -m "feat: surface Nominal PR in run-record sigma rows"
```

---

## Task 4: `consolidate.py` — row definitions, color, pivot builder

**Files:**
- Create: `cert_data_process/analysis/__init__.py` (empty)
- Create: `cert_data_process/analysis/consolidate.py`
- Test: `tests/test_consolidate.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
from cert_data_process.analysis.consolidate import PR_ROWS, pr_color, consolidate_pr

def test_pr_color_bands():
    assert pr_color(100.0) == "green"
    assert pr_color(95.0) == "green"
    assert pr_color(94.9) == "amber"
    assert pr_color(90.0) == "amber"
    assert pr_color(89.9) == "red"
    assert pr_color(None) == "none"

def test_pr_rows_cover_all_slide_rows():
    labels = [r["label"] for r in PR_ROWS]
    assert labels == ["hold", "ocv_const_hold", "delay", "ocv_delay_early",
                      "ocv_delay_late", "delay_mns", "delay_skn", "delay_std",
                      "trans", "ocv_trans_early", "ocv_trans_late",
                      "trans_mns", "trans_skn", "trans_std"]

def _rec():
    return {
        "batch_id": "B3", "config": {"vt_type": "svt", "library_type": "mb"},
        "sigma": [
            {"corner": "ssgnp_0p475v_0c", "type": "delay", "nomBase": 100.0, "nomW1": 100.0,
             "eBase": 100.0, "eW1": 100.0, "lBase": 92.59, "lW1": 92.7, "health": "OK"},
            {"corner": "ssgnp_0p475v_0c", "type": "hold", "nomBase": 100.0, "nomW1": 100.0,
             "lBase": 91.49, "lW1": 91.5, "health": "OK"},
        ],
        "moments": [
            {"corner": "ssgnp_0p475v_0c", "type": "delay", "ms": 99.64, "std": 99.89, "skew": 100.0,
             "msW1": 99.64, "stdW1": 99.89, "skewW1": 100.0, "health": "OK"},
        ],
    }

def test_consolidate_builds_columns_and_cells():
    piv = consolidate_pr([_rec()], basis="w1")
    col = piv["columns"][0]
    assert col["batch_id"] == "B3" and col["vt"] == "svt" and col["libtype"] == "mb"
    assert col["corner"] == "ssgnp_0p475v_0c"
    cells = piv["cells"]                      # {(row_label, col_index): {pr, color}}
    assert cells[("ocv_delay_late", 0)]["pr"] == 92.7
    assert cells[("ocv_delay_late", 0)]["color"] == "amber"
    assert cells[("delay", 0)]["pr"] == 100.0 and cells[("delay", 0)]["color"] == "green"
    assert cells[("delay_skn", 0)]["pr"] == 100.0      # moments Skew (w1)
    assert cells[("ocv_const_hold", 0)]["color"] == "amber"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_consolidate.py -v`
Expected: FAIL — `ModuleNotFoundError: cert_data_process.analysis.consolidate`.

- [ ] **Step 3: Create the module**

Create `cert_data_process/analysis/__init__.py` (empty file).

Create `cert_data_process/analysis/consolidate.py`:

```python
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


def consolidate_pr(records: list[dict], basis: str = "w1",
                   green_low: float = GREEN_LOW, amber_low: float = AMBER_LOW) -> dict[str, Any]:
    """Build the pivot: ordered columns (one per batch x corner) and a cell map.

    cells[(row_label, col_index)] = {"pr": float|None, "color": str, "health": str}
    """
    columns: list[dict] = []
    sig_idx: dict[int, dict] = {}
    mom_idx: dict[int, dict] = {}

    for rec in records:
        cfg = rec.get("config", {})
        batch_id = rec.get("batch_id") or rec.get("name", "?")
        vt = cfg.get("vt_type", "")
        libtype = cfg.get("library_type", "auto")
        corners = []
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

    cells: dict[tuple, dict] = {}
    for ci, _col in enumerate(columns):
        for row in PR_ROWS:
            sig = sig_idx[ci].get((columns[ci]["corner"], row["type"]))
            mom = mom_idx[ci].get((columns[ci]["corner"], row["type"]))
            pr = _value(row["metric"], basis, sig, mom)
            health = (sig or mom or {}).get("health", "UNKNOWN")
            cells[(row["label"], ci)] = {
                "pr": pr, "color": pr_color(pr, green_low, amber_low), "health": health,
            }
    return {"columns": columns, "rows": PR_ROWS, "cells": cells, "basis": basis}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest tests/test_consolidate.py -v`
Expected: PASS (all 4 tests).

- [ ] **Step 5: Commit**

```bash
git add cert_data_process/analysis/__init__.py cert_data_process/analysis/consolidate.py tests/test_consolidate.py
git commit -m "feat: add consolidate_pr pivot builder for multi-batch Table 1"
```

---

## Task 5: `outliers.py` — per-cell outlier breakdown from per-arc rows

**Files:**
- Create: `cert_data_process/analysis/outliers.py`
- Test: `tests/test_outliers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_outliers.py
from cert_data_process.analysis.outliers import outlier_breakdown

def _arc(cell, mc, lib, status):
    # mimics one row of *_sigma_check_with_waivers.csv for metric prefix "Late_Sigma"
    return {
        "Arc": f"combinational_{cell}_Z_rise_A_rise_NO_CONDITION_3_5",
        "Late_Sigma_MC_value": str(mc),
        "Late_Sigma_Lib_value": str(lib),
        "Late_Sigma_Final_Status": status,
    }

def test_outlier_breakdown_counts_cells_polarity_and_worst():
    rows = [
        _arc("INVD1", 40.0, 38.0, "Fail"),   # optimistic (lib<mc), abs 2.0, rel 5%
        _arc("INVD1", 40.0, 39.0, "Fail"),   # optimistic, same cell
        _arc("ND2D2", 50.0, 60.0, "Fail"),   # pessimistic (lib>mc), abs 10.0, rel 20%
        _arc("BUFD4", 30.0, 30.1, "Pass"),   # passing -> excluded
    ]
    r = outlier_breakdown(rows, "Late_Sigma")
    assert r["n_outlier_cells"] == 2                 # INVD1, ND2D2 (BUFD4 passed)
    assert r["worst_err_ps"] == 10.0                 # |60-50|
    assert round(r["worst_rel_pct"], 1) == 20.0      # 10/50
    assert r["polarity"] == "mixed"                  # 2 opt arcs, 1 pess arc
    assert r["n_optimistic"] == 2 and r["n_pessimistic"] == 1

def test_outlier_breakdown_all_pass_is_empty():
    rows = [_arc("INVD1", 40.0, 40.0, "Pass")]
    r = outlier_breakdown(rows, "Late_Sigma")
    assert r["n_outlier_cells"] == 0 and r["worst_err_ps"] is None and r["polarity"] == "none"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_outliers.py -v`
Expected: FAIL — `ModuleNotFoundError: cert_data_process.analysis.outliers`.

- [ ] **Step 3: Create the module**

Create `cert_data_process/analysis/outliers.py`:

```python
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
        v = float(str(s).strip())
    except (ValueError, TypeError):
        return None
    return v


def _cell_of(arc: str) -> str:
    parts = str(arc).split("_")
    return parts[1] if len(parts) > 1 else str(arc)


def _is_pass(status: str) -> bool:
    return str(status).strip().lower() in ("pass", "passed", "true")


def outlier_breakdown(per_arc_rows: list[dict], metric_prefix: str) -> dict[str, Any]:
    """Summarize the failing arcs for one metric.

    Returns: n_outlier_cells, n_outlier_arcs, polarity (optimistic/pessimistic/
    mixed/none), n_optimistic, n_pessimistic, worst_err_ps, worst_rel_pct.
    """
    mc_k = f"{metric_prefix}_MC_value"
    lib_k = f"{metric_prefix}_Lib_value"
    st_k = f"{metric_prefix}_Final_Status"

    cells, n_opt, n_pess = set(), 0, 0
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest tests/test_outliers.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add cert_data_process/analysis/outliers.py tests/test_outliers.py
git commit -m "feat: add outlier_breakdown (cells/polarity/worst-error) for Table 2"
```

---

## Task 6: Full-suite regression + push

**Files:** none (verification only)

- [ ] **Step 1: Run the whole suite**

Run: `PYTHONPATH=. python -m pytest tests/ -q`
Expected: PASS — previous 42 plus the new Nominal/consolidate/outliers tests.

- [ ] **Step 2: Confirm no legacy import broke**

Run: `python -m py_compile 2-data_process/get_PR/Sigma/check_sigma_with_waivers.py && PYTHONPATH=. python -c "import cert_data_process.analysis.consolidate, cert_data_process.analysis.outliers; print('imports OK')"`
Expected: `imports OK`.

- [ ] **Step 3: Push (after user confirmation, per CLAUDE.md §5)**

```bash
git push origin main
```

---

## Self-review

**Spec coverage (Phase B scope):**
- Nominal PR (§1, §4.3) → Tasks 1–3. ✅
- Consolidated pivot model + thresholds (§2, §4.2) → Task 4. ✅
- Outlier breakdown self-populated from per-arc data (§4.4) → Task 5. ✅
- Multi-batch *config/run UI* (§4.1, Phase C), Table-1 *view* (D), Table-2 *view* (E), scatter (F) → **out of scope for this plan** (later plans), as intended.

**Placeholder scan:** none — every step has runnable code/commands and expected output.

**Type consistency:** record-row fields (`nomBase/nomW1`, `eBase/eW1`, `lBase/lW1`, `ms/std/skew`, `msW1/stdW1/skewW1`) match the existing `build_sigma_rows`/`build_moments_rows` shapes in `web/summary.py`; `consolidate_pr` reads exactly those. `outlier_breakdown` reads `{prefix}_MC_value`/`{prefix}_Lib_value`/`{prefix}_Final_Status`, the real per-arc CSV columns from `check_sigma_with_waivers.py`. Color bands match `pr_color` everywhere (green≥95, amber 90–95, red<90).

**Note for executor:** Tasks 1–2 edit the legacy pandas script; run them on a machine with pandas. Tasks 3–5 are stdlib-only and run anywhere. The per-arc CSV→`outlier_breakdown` wiring (which file to read per metric/corner) is a thin reader that belongs with the Table-2 *view* (Phase E), not here — Task 5 keeps the core pure and testable.
```
