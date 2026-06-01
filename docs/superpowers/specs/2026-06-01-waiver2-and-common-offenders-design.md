# Design Spec — Waiver_2 (abs_tol) + Common-Offenders Analysis

**Date:** 2026-06-01
**Status:** DRAFT — awaiting user review before writing-plans
**Author:** Claude (brainstorming, continued from waiver/outlier discussion)

> Two related deliverables planned together. **Part A — Waiver_2** (user-assigned
> absolute tolerance for hold sigma). **Part B — Common-Offenders** (cross-corner
> and cross-batch outlier commonality). Both build on the already-implemented
> pass-rate flow and the `analysis/` layer. Waiver_3 (Voltage Margin) and the
> GUI waiver-level toggle are separate, later specs.

---

## Part A — Waiver_2 (abs_tol)

### A.0 Definition
A user-assigned **absolute tolerance** in ps. A hold arc whose `|Lib − MC|` is within
the tolerance is waived. Captures "the lib is off, but by an amount we accept for
this library." Per CLAUDE.md, abs_tol values are **user-provided, never inferred
or placeholdered**.

### A.1 Scope (locked)
- **Hold `Late_Sigma` only.** Not delay/slew, not hold Nominal, not mpw.
- **Per-corner granularity.** 1 batch ≠ 1 library — corners within a batch can map
  to different libs — so abs_tol is a mapping `{corner: abs_tol_ps}`, not one value
  per batch. A corner with no entry gets no W2 (tolerance 0 → W2 is a no-op there).
- **Stacks on base+W1.** An arc passes-with-W2 if `base_pass OR waiver1 OR (hold &&
  |Lib−MC| ≤ abs_tol[corner])`.

### A.2 Where it lives
- **Config:** add `abs_tol_ps_by_corner: dict[str, float]` to `CertDataProcessConfig`
  (default `{}`). Threaded through `build_config`, CLI (`--abs-tol-ps corner=val ...`),
  executor, and `to_manifest_dict`. Empty = waiver_2 inactive (fully backward-compatible).
- **Pass logic:** `check_sigma_with_waivers.check_pass_with_waivers` gains an optional
  `abs_tol_ps` param. New result field `waiver2_abs_tol: bool` computed only for
  hold Late_Sigma: `(type_name == 'hold' and param_name == 'Late_Sigma' and
  abs_tol_ps and abs(lib_value - mc_value) <= abs_tol_ps)`. For every other
  type/param it is `False`.
- **PR table:** add a `Late_Sigma_PR_with_Waiver2` column for hold (and a combined
  `PR_with_Waiver1_2 = base OR W1 OR W2`). The existing Base/W1 columns are unchanged.
- **Run record / summary:** `build_sigma_rows` reads the new column into `lW2`
  (and `lW12`) so the GUI basis selector can show it.

### A.3 GUI (Setup)
A small editable table under the corners editor: one row per configured corner with
an `abs_tol (ps)` entry (blank = none). Gathered into `abs_tol_ps_by_corner`.
(The full Base/+W1/+W2 *display* toggle is the separate waiver-level-toggle spec;
this spec only needs the **input** + the computed column.)

### A.4 Testing
- `check_pass_with_waivers`: hold Late_Sigma with `|dif| ≤ abs_tol` → `waiver2_abs_tol
  True`, and an arc failing base+W1 but within abs_tol counts as pass-with-W2.
- abs_tol applies **only** to hold Late_Sigma: a delay arc with the same dif and an
  abs_tol set → `waiver2_abs_tol False`.
- Empty `abs_tol_ps_by_corner` → identical output to today (regression).
- Config round-trips abs_tol through `to_manifest_dict`.

---

## Part B — Common-Offenders (cross-corner / cross-batch)

### B.0 Problem
A single (corner, metric) scatter can't tell a **systematic** lib problem (a cell
failing across many corners/batches) from a **localized** one (failing in a single
corner). Common-offenders aggregates outliers across contexts to rank the systematic
ones first — the fastest path to "fix these N cells and the PR jumps."

### B.1 Granularity (locked)
Three selectable keys:
- **cell** — `arc_parts[1]`.
- **cell+arc** — the full arc string (same cell, same exact arc across contexts).
- **cell+table_point** — `(cell, index1, index2)` (same cell + same slew/load grid point).

### B.2 Scope (locked)
A "context" = one `(batch, corner)` pair for a given metric. The set of contexts =
**the batches currently selected in History** (else all), × their corners — the same
selection model `_pr_records()` already uses. (Open: same-VT-only vs any — defaulting
to "any selected".)

### B.3 Core function (pure, `analysis/common.py`)
```
common_offenders(per_arc_by_context, metric, key="cell") -> list[dict]
```
- `per_arc_by_context`: `{(batch_id, corner): [per_arc_rows]}` — the GUI loads these
  via `perarc.find_per_arc_csv` + `perarc.load_rows` per (batch, corner) for the metric.
- Returns one dict per offender key:
  `{key fields, n_contexts, contexts:[(batch_id,corner), ...], n_fail_total,
    worst_rel_pct, worst_err_ps, polarity}` — sorted by `n_contexts` desc, then
  `worst_rel_pct` desc.
- Reuses `outliers._failing` for the per-context failing rows; pure + unit-tested.

### B.4 GUI
A new section/tab "Common offenders" with: a metric selector, a granularity selector
(cell / cell+arc / cell+table_point), and a ranked table
(`key | #contexts | #fails | worst rel% | polarity`). Double-click an offender →
list its contexts (which batch·corner it appears in); from there, open the existing
per-(corner,metric) scatter with that key highlighted. Reuses the enriched panel.

### B.5 Testing
- `common_offenders` with synthetic two-context data: a cell failing in both contexts
  ranks above one failing in a single context; `n_contexts`/`contexts` correct.
- The three granularity keys aggregate correctly (cell vs cell+arc vs cell+table_point).
- polarity aggregation (optimistic/pessimistic/mixed) across contexts.

### B.6 Out of scope
- Clustering / ML grouping (rankings are explicit counts).
- Auto-deciding "systematic" vs "localized" (we present #contexts; the user judges).

---

## Self-review
- **Coverage:** waiver_2 (abs_tol per corner, hold late-sigma, stacks on base+W1,
  user-provided) → Part A. Cross-corner + cross-batch commonality at 3 granularities
  → Part B. Both pinned by user answers this session.
- **Placeholders:** none; abs_tol is explicitly user-input-only.
- **Consistency:** waiver_2 reuses `check_pass_with_waivers` (same engine as base/W1,
  no second pass-rate path — per "use our implemented pass rate"). Common-offenders
  reuses `outliers._failing`, `_cell_of`, `arc_indices`, and the existing
  History-selection model (`_pr_records`) + scatter panel.
- **Ambiguity flagged:** B.2 same-VT-vs-any scope — defaulting to "any selected",
  to confirm.
