# Design Spec — Multi-Batch PR Status + Deep Outlier Analysis

**Date:** 2026-06-01
**Status:** DRAFT — awaiting user review (written overnight; decisions marked ⚠️ need a yes/no)
**Author:** Claude (per /goal, superpowers brainstorming flow)

---

## 0. The goal (from the two target slides)

The user's ultimate deliverable is a tool that, after configuring and running **3 batches with different VT**, produces — end to end, no manual spreadsheet work — **two tables** and a **drill-down scatter**:

### Target Table 1 — "Current PR Status" (consolidated pivot)
A single matrix, **every data-type down the left, every (batch · VT · base/MB · corner) across the top**, measured against the FMC golden.

- Legend on slide: *"PR = rel_err criterion + waiver 1 (CI enlargement) vs FMC golden. green ≥ 99% · amber 90%–95% · red < 90%. Waiver 2&3 not Applied Yet."*
- Columns observed: `B1·SVT·base` {0p450 m40c, 0p465 m40c, 0p480 m40c, 0p495 m40c}; `B2·ELVT` {ffgnp 125c}; `B2·SVT` {0p475 0c, 0p515 0c}; `B3·ELVT·MB` {ffgnp 125c}; `B3·SVT` {0p475 0c, 0p515 0c}.
- Rows observed, in two groups:
  - **CONS · hold arcs:** `hold`, `ocv_const_hold`
  - **NON_CONS · delay·slew arcs:** `delay`, `ocv_delay_early`, `ocv_delay_late`, `delay_mns`, `delay_skn`, `delay_std`, `trans`, `ocv_trans_early`, `ocv_trans_late`, `trans_mns`, `trans_skn`, `trans_std`

### Target Table 2 — "Sub-95% points — cell/arc-level breakdown"
For every point **below threshold** in Table 1, one row with: `Metric`, `Class` (cons/non_cons), `Batch·Corner`, `PR (%)`, `# outlier cells`, `Polarity (opt/pess)`, `Worst err (ps)`, `Rel err (%)`.
- Slide note: *"Skeleton — populated from Cadence outlier list (Steve); pending = awaiting list. Polarity / worst-error quantify each point beyond its PR."*

### Target interaction — scatter drill-down
*"Every point that didn't pass the line is clickable → see a scatter plot of the outlier distribution."*

---

## 1. Row-name → existing-metric mapping (key insight)

The slide's row names map onto data the pipeline already computes per (corner, type), **plus one new thing (nominal PR)**:

| Slide row | Source type | Metric in our data |
|-----------|-------------|--------------------|
| `delay` | delay | **Nominal** (NEW) |
| `ocv_delay_early` | delay | Early_Sigma |
| `ocv_delay_late` | delay | Late_Sigma |
| `delay_mns` | delay | Meanshift |
| `delay_skn` | delay | Skew |
| `delay_std` | delay | Std |
| `trans` | slew | **Nominal** (NEW) |
| `ocv_trans_early` | slew | Early_Sigma |
| `ocv_trans_late` | slew | Late_Sigma |
| `trans_mns` / `trans_skn` / `trans_std` | slew | Meanshift / Skew / Std |
| `hold` | hold | **Nominal** (NEW) |
| `ocv_const_hold` | hold | Late_Sigma |

**Implication:** we already produce Early/Late sigma + Meanshift/Std/Skew per type. We are **missing the per-type Nominal pass rate** (lib nominal vs MC nominal). The lib-join already extracts `*_Nominal` (it runs `-nominal_check`), so this is a check-script + summary addition, not a lib-join change.

---

## 2. Threshold / color decision ⚠️ (Q1)

The slide legend says `green ≥ 99% · amber 90%–95% · red < 90%`, but the **actual cell coloring contradicts it**: `96.78`, `98.22`, `95.44` render green while `94.51`, `92.59`, `91.49` render amber. So the real bands are:

- **green ≥ 95**, **amber 90–95**, **red < 90** (matches our existing `PASS_THRESHOLD = 95`).

**Decision:** make the two cutoffs configurable (`amber_low = 90`, `green_low = 95`), default to the observed 95/90 bands. The "99" in the legend is treated as a typo. **⚠️ Q1: confirm green≥95 / amber 90–95 / red<90, or do you actually want green≥99?**

---

## 3. Architecture overview

```
Setup: define N batches (B1/B2/B3) ── each: vendor, VT, library_type(base/mb),
         corners, fmc input ──► [select which to run] ──► JobManager (concurrency-fixed)
                                                              │
                                   per batch: run_record.json + per-arc CSVs
                                                              │
            ┌─────────────────────────────────────────────────┘
            ▼
  Consolidate (NEW): read N run_records ──► PR pivot model
            │                                  (rows=metric, cols=batch·corner, +Nominal)
            ├─► Table 1 view (colored pivot, export CSV)
            │
            └─► Outlier model (NEW): for each sub-threshold cell, read that
                 (batch,corner,metric) per-arc CSV ──► #outlier cells, polarity,
                 worst err (ps), rel err (%)
                      │
                      ├─► Table 2 view (sub-threshold breakdown, export CSV)
                      └─► click a failing cell ──► Scatter (lib vs MC, threshold band,
                                                   outliers highlighted) — Tkinter Canvas
```

All per-arc data needed for Table 2 and the scatter **already exists** in
`combined/sigma/*_sigma_check_with_waivers.csv` (columns per param: `*_MC_value`,
`*_Lib_value`, `*_MC_CI_LB/UB`, `*_abs_err`, `*_rel_err`, `*_Error_Direction`,
`*_Final_Status`) and the moments equivalents. Nothing new needs recomputing for
drill-down — we read these on demand.

---

## 4. Component designs

### 4.1 Multi-batch config & run (Phase C)
- **Setup** gains a **batch list**: add/edit/remove batch entries, each carrying the existing config (vendor, process, version, **vt_type**, **library_type** base/mb, corners, fmc_mode, fmc dir, lib dir). Reuse the fields we already built (VT/RC/library_type).
- A **"Run selected"** action submits the checked batches to the existing `JobManager` (already concurrency-capable; lib-join is now correctness-safe). 1 batch = 1 EDA recipe, as today.
- **Pipeline/Log view** becomes multi-run aware: one collapsible progress block per batch, each with its stage states + log tail. (Today it tracks a single active job.)
- Batches persist to the runs store; **History** already lists them; **Compare** already diffs them.
- ⚠️ **Q2:** Is a batch = (one VT, one library_type, a set of corners)? i.e. B1·SVT·base is one batch with 4 corners; B3 has both ELVT·MB and SVT — is B3 *one* batch (mixed) or *two*? The slide groups B3 into `B3·ELVT·MB` and `B3·SVT`, suggesting **a "batch" in the table = (batch_id × VT × base/MB)**. Proposed model: the tool's run unit stays one (vendor,VT,library_type,corners) config; the Table-1 column group label is `{batch_id}·{VT}·{base|MB}`. You tag each run with a `batch_id` (B1/B2/B3) so the pivot can group them. **Confirm this grouping key.**

### 4.2 Consolidated PR pivot — Table 1 (Phase B+D)
- New `consolidate_pr(records, thresholds)` builds the matrix: ordered metric rows (§1), ordered columns = each run's (batch_id, VT, base/MB, corner). Cell = the metric's PR (Base or +Waiver1 — slide uses **+Waiver1**, default basis = w1).
- Color per §2. Blank/`—` when a metric doesn't apply (e.g. hold has only Nominal + Late) or NO_DATA.
- Coverage/health still tracked underneath; a NO_DATA cell is visually distinct from a low PR (honest-logging rule).
- **Export CSV** = the full pivot (copiable), matching Table 1 layout.
- ⚠️ **Q3:** Table 1 uses **PR_with_Waiver1** (per the legend "rel_err + waiver 1"). Confirm default basis = Waiver1 (with a Base/​W1 toggle like today).

### 4.3 Nominal PR (Phase B)
- Add `Nominal` as a checked param in `check_sigma_with_waivers.py` for delay/slew/hold (lib `*_Nominal` vs `MC_Nominal`). Same coverage/Data_Health treatment.
- ⚠️ **Q4:** Nominal pass criterion + threshold. Proposed: same rel_err-or-CI logic, rel threshold = 3% (delay/hold), 6% (slew) — mirroring sigma. Or a dedicated nominal tolerance? (Slide shows nominal ≈ 100% everywhere, so it's lenient in practice.)

### 4.4 Outlier breakdown — Table 2 (Phase B+E)
For each Table-1 cell **below `green_low`** (or below a separate "investigate" cutoff ⚠️ Q5), compute from that (batch,corner,metric) per-arc CSV:
- **# outlier cells** = count of distinct **cells** (parsed from `Arc` → `arc_parts[1]`) that have ≥1 failing arc (`*_Final_Status` = fail / not pass under the chosen basis).
- **Polarity (opt/pess)** = from `*_Error_Direction`: optimistic = lib<mc, pessimistic = lib≥mc; report the dominant direction (and counts).
- **Worst err (ps)** = max |`*_abs_err`| among failing arcs.
- **Rel err (%)** = max |`*_rel_err`| among failing arcs ×100.
- Rows ordered worst-PR-first. **Export CSV.**
- The slide's "populated from Cadence outlier list (Steve)" → we **self-populate from our own per-arc data** (we have it all), removing the dependency on Steve's list. The external Cadence list becomes an *optional reconciliation/overlay* tied to waiver_2 (Phase G). ⚠️ **Q6:** OK to self-populate (vs strictly mirroring Steve's list)?

### 4.5 Scatter drill-down — Table 3 (Phase F)
- Click a red/amber cell in Table 1 (or a Table 2 row) → open a scatter for that (batch, corner, metric).
- **Plot:** x = MC value, y = Lib value, one point per covered arc; draw the y=x line and the pass band (CI bounds / rel-err threshold); **outliers (failing arcs) highlighted red**, passing arcs muted. Hover/click a point → its Arc (cell + pin + when + indices).
- Alt view toggle: rel_err distribution (rel_err per arc, threshold line) — useful to see how far out the tail is.
- **Tech:** Tkinter **Canvas** (stdlib, guaranteed on the air-gapped host) renders the scatter — no matplotlib dependency. If matplotlib is importable we *may* offer a richer embedded plot, but the Canvas path is the contract. ⚠️ **Q7:** Canvas-based scatter acceptable, or do you require matplotlib-quality plots (PNG export)?

### 4.6 Cadence outlier list / waiver_2 (Phase G — future)
- Ingest Steve's Cadence outlier list; reconcile against our self-computed outliers; this is also where **waiver_2 (abs_tol per library)** plugs in (user-provided values, never auto-inferred — per CLAUDE.md). Deferred; not in the first build.

---

## 5. Phased implementation plan

- **Phase A — Concurrency fix** ✅ DONE overnight (serial default + per-job TMPDIR). Prerequisite for trustworthy multi-batch numbers.
- **Phase B — Backend data layer:** add Nominal PR (check script + summary); `consolidate_pr()` pivot builder; `outlier_breakdown()` reading per-arc CSVs. Pure functions, unit-tested. *No UX lock-in.*
- **Phase C — Multi-batch config/run:** Setup batch list + "Run selected"; multi-run Pipeline/log view; `batch_id` tagging.
- **Phase D — Table 1 view:** colored consolidated pivot + CSV export.
- **Phase E — Table 2 view:** sub-threshold outlier breakdown + CSV export.
- **Phase F — Scatter drill-down:** Canvas scatter from a clicked failing cell.
- **Phase G — (future)** Cadence outlier list ingest + waiver_2/waiver_3.

Each phase is independently testable; B is the foundation and can land first with tests even before the UI.

---

## 6. Assumptions if no answer by build time
If you haven't answered the ⚠️ questions when I (with your go-ahead) start building, I will use these defaults and flag each in the code/PR:
1. Thresholds: green≥95, amber 90–95, red<90 (configurable).
2. Batch grouping key = `{batch_id}·{VT}·{base|MB}`; run unit = one (vendor,VT,library_type,corners).
3. Table 1 default basis = PR_with_Waiver1, with Base/W1 toggle.
4. Nominal criterion mirrors sigma (rel 3% delay/hold, 6% slew, OR within CI).
5. Outlier breakdown shown for cells below green_low (95).
6. Self-populate Table 2 from our per-arc data; Cadence list = later overlay.
7. Tkinter Canvas scatter (stdlib); matplotlib optional.

---

## 7. Spec self-review
- **Placeholders:** none; open decisions are explicit ⚠️ Q1–Q7 with defaults.
- **Consistency:** row→metric map (§1) is the spine; Tables 1/2 and scatter all read the same per-(batch,corner,metric) data; nominal is the only new computation.
- **Scope:** large but cleanly decomposed (A–G); A done, B is a self-contained, testable foundation. Not a single mega-PR.
- **Ambiguity:** the main ambiguities (thresholds, batch grouping, basis, nominal tolerance, outlier cutoff, plot tech) are isolated as Q1–Q7 so review is yes/no, not open-ended.

---

**NEXT STEP after your approval:** run the writing-plans skill on this spec to produce the detailed Phase-B implementation plan (tasks, files, tests), then execute.
