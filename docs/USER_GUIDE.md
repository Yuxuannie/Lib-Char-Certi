# Lib-Char-Certi — User Guide (v1.0)

A desktop tool for **certifying a characterized standard-cell library** against
Monte-Carlo / FMC reference data. It computes pass-rate (PR) tables, flags
sub-threshold corners, and lets two parties (the library team and the EDA vendor)
**drill into any failing point down to the source `.lib` cell and FMC input row**
— so an outlier can be cross-checked, not just counted.

This guide walks the whole flow on bundled demo data; no real inputs required.

---

## 1. Launch

The tool is a single Tkinter process — no server, no port. It displays over
X11 / Exceed like a terminal.

```bash
# From the repo root, on a host whose Python has Tkinter:
python -m cert_data_process.app            # normal: reads ./certi_runs
python -m cert_data_process.app --demo     # open the bundled demo (no data needed)
```

> **First time? Use `--demo`.** It loads a synthetic batch (`N2P v1.0 CDNS Best
> (DEMO)`) so you can click through every screen before touching real data. The
> demo numbers are fabricated but internally consistent — every PR matches the
> per-arc data behind it.

If you see `ERROR: this Python has no Tkinter`, pick a Python built with Tk (most
EDA host Pythons have it; a stock `python3` usually works).

---

## 2. The tabs at a glance

| Tab | What it answers |
|-----|-----------------|
| **Setup** | What library / corners / FMC am I certifying? → **Run certification** |
| **Pipeline** | Is the run progressing? Any per-stage audit findings? |
| **Results** | For the loaded batch: does each timing type PASS (≥95%)? |
| **PR Status** | Consolidated PR pivot across all (or selected) batches |
| **Outliers** | Which (metric, corner) points are sub-95%, and how do they fail? |
| **Common** | Which cells/arcs fail across *multiple* corners or batches? |
| **History** | All past runs; select/▢-check batches to scope the other tabs |
| **Compare** | Diff metrics across batches |

> The **Analysis (Voltage Margin)** tab is intentionally hidden in v1.

---

## 3. Five-minute demo tour

Launch with `--demo`, then:

### 3.1 History → open the batch
Go to **History**. You'll see one row: `N2P v1.0 CDNS Best (DEMO)`, vendor `cdns`,
mean Late-Sigma `93.8%`, status `passed`. Double-click it to load it into Results.

![History](images/07_history.png)

### 3.2 Results — the verdict, and how waivers move it
The **Results** tab groups PR by timing type (delay / slew / hold). Cells are
green ≥95%, amber 90–95%, red <95%. Toggle the **basis** radios at the top:

| Basis | Demo verdict | Why |
|-------|--------------|-----|
| **Base** | ❌ FAIL — 3 metrics <95% | raw pass rate |
| **+Waiver1** (CI +6%) | ❌ FAIL — hold still 92% | CI enlargement recovers delay, not hold |
| **+Waiver2** (abs_tol) | ✅ PASS | abs_tol (15 ps) waives the 4 marginal hold arcs |

This is the core story: a library that fails raw can certify once the agreed
waivers are applied — and the tool shows exactly which arcs each waiver rescued.

![Results](images/02_results.png)

### 3.3 PR Status — consolidated pivot
**PR Status → Build.** Rows are data-types (`ocv_const_hold`, `ocv_delay_late`,
…), columns are each batch × corner. On `+Waiver1` basis the demo shows
`ocv_const_hold @ ssgnp_0p675v_125c` amber at **92.0%** — everything else green.

![PR Status](images/03_pr_status.png)

### 3.4 Outliers — what's actually failing
**Outliers → Build** (try the **Base** basis to see the most points). Each row is
a sub-95% (metric, corner) with its failure breakdown: `#cells`, `#opt`
(optimistic = Lib<MC, library claims *better* than silicon), `#pess`, polarity,
worst error. For the demo hold point you'll see **6 cells, 3 opt / 3 pess, worst
rel-err 23.3%**.

> A `?` in a breakdown column means the per-arc CSV for that corner/type wasn't
> found (not a failure — just no detail to expand). The hint line under the table
> explains this.

![Outliers](images/04_outliers.png)

### 3.5 Outlier scatter + source trace-back — the cross-check
**Double-click an Outliers row** to open the drill-down: a Lib-vs-MC scatter (with
a residual / rel-error view and Normal/Log scale), plus ranked lists of the worst
cells, table-points, and arcs. **Double-click a worst-arc** to open its detail:

- exact MC value, Lib value, signed error, abs error, rel-error (with the engine
  denominator), and direction (optimistic / pessimistic);
- a **Trace back to source** panel: **Copy path** or **Peek** straight into the
  source `.lib` cell block (the whole brace-balanced `cell (…) { … }`) and the FMC
  input rows for that cell — the exact lines both parties need to agree on.

This is the workflow two teams use to settle "is this outlier real?" without
emailing files back and forth.

![Outlier scatter](images/06_scatter.png)

> If `matplotlib` isn't installed, the scatter degrades to a built-in Canvas plot
> — the rankings and source trace-back work either way.

### 3.6 Common offenders — systematic vs one-off
**Common** finds cells/arcs that fail across *multiple* contexts (corners/batches),
grouped by cell, cell+arc, or cell+table-point. Select several batches in History
first to compare recipes. Double-click an offender to see every place it fails.

![Common](images/05_common.png)

---

## 4. Running your own data (Setup tab)

| Field | Notes |
|-------|-------|
| **Vendor** | `cdns` or `snps` (sets default lib unit) |
| **Process / version** | e.g. `n2p` / `v1p0` |
| **Corners** | add each corner; or pull from History |
| **Timing types** | delay / slew / hold / mpw |
| **VT / RC type, Library type** | metadata for the run record |
| **FMC unit / Lib unit** | inputs are converted to ps internally; defaults track vendor/format |
| **abs_tol ps (hold)** | Waiver_2. One value for all corners, or `c1=19.5, c2=20`. **Blank = off.** If you type something unparseable, the tool now *warns* instead of silently disabling W2. |
| **FMC input** | Decks (parse) / Parsed DFDS / Parsed SCLD — the FMC-dir label updates to match |
| **FMC dir / Lib dir** | Browse to the inputs |

Click **▶ Run certification** → watch **Pipeline** → results land in **Results**.
Moments (meanshift / std / skew) are derived from the FMC data — no Full-MC run
is needed.

---

## 5. Waivers — terminology

- **Base PR** — raw pass rate, no waivers.
- **Waiver1** — CI bounds enlarged 6% (the engine's `Waiver1_CI_Enlarged`).
- **Waiver2** — `abs_tol` (ps), **hold Late_Sigma only**, stacked on Base+W1; you
  supply the value. The tool never invents it.

(Waiver3 is handled downstream by the separate Voltage-Margin tool and is out of
scope here.)

---

## 6. Screenshots in this guide

The figures live in `docs/images/`. To (re)generate them against the demo on a
machine with a display:

```bash
python scripts/make_demo_screenshots.py     # needs Tkinter + a display
```

On macOS this needs Screen-Recording permission for your terminal; on Linux it
uses ImageMagick's `import`. If a figure is missing, the step text above still
describes exactly what you'll see.

To regenerate the demo data itself:

```bash
python scripts/make_demo_run.py
```
