# Lib-Char-Certi — User Guide (v1.0)

A desktop tool for **certifying a characterized standard-cell library** against
Monte-Carlo / FMC reference data. It computes pass-rate (PR) tables, flags
sub-threshold corners, and lets two parties (the library team and the EDA vendor)
**drill into any failing point down to the source `.lib` cell and FMC input row**
— so an outlier can be cross-checked, not just counted.

This guide walks the whole flow on real inputs, from Setup through the outlier
cross-check.

---

## Table of contents

1. [Requirements](#1-requirements)
2. [Install](#2-install)
3. [Prepare your input folder](#3-prepare-your-input-folder)
4. [Launch](#4-launch)
5. [The tabs at a glance](#5-the-tabs-at-a-glance)
6. [Step-by-step: certifying your library](#6-step-by-step-certifying-your-library)
7. [Waivers — terminology](#7-waivers--terminology)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Requirements

| Component | Requirement |
|-----------|-------------|
| **Python** | **3.9 or newer** (developed/tested on 3.9–3.11). The repo pins `requires-python = ">=3.9"`. |
| **Tkinter** | Required for the desktop console. It ships with most CPython builds; most EDA host Pythons already have it. Verify with `python -c "import tkinter"`. |
| **pandas / numpy** | Required for real certification runs (parsing FMC data and computing PR). |
| **matplotlib** | *Optional* — enriches the outlier scatter. Without it the GUI falls back to a built-in Canvas plot. |
| **EDA `ldbx`** | Required only for the **lib-join / combine** step against real `.lib` decks. It is provided by your EDA environment and is **not** installable from PyPI. |

Check your Python version before anything else:

```bash
python --version        # must print 3.9.x or newer
python -c "import tkinter; print('tkinter ok')"
```

---

## 2. Install

From the repository root:

```bash
# Core install (editable):
pip install -e .

# With the optional scatter plotting extra:
pip install -e ".[plots]"      # or simply: pip install matplotlib
```

> On EDA hosts without PyPI access, use the interpreter your flow already provides
> (it normally has pandas/numpy/Tkinter and the `ldbx` module). You do not need to
> reinstall those.

---

## 3. Prepare your input folder

Put your real inputs under the `input/` folder at the repo root (create it if it
doesn't exist). The tool never modifies your inputs — it only reads them and writes
results under `./certi_runs`.

A typical layout:

```
input/
├── fmc/        # FMC reference data — decks to parse, or pre-parsed DFDS / SCLD
└── lib/        # the characterized .lib files to certify
```

You point the tool at these two directories from the **Setup** tab (the **FMC dir**
and **Lib dir** browse buttons). The folder names above are only a suggestion —
any path works, as long as you browse to it in Setup.

The **FMC input mode** you pick in Setup decides what the **FMC dir** should
contain:

| FMC input mode | What `input/fmc/` should hold |
|----------------|-------------------------------|
| **Decks (parse)** | raw FMC decks; the tool parses them |
| **Parsed DFDS** | already-parsed DFDS output |
| **Parsed SCLD** | already-parsed SCLD golden data (note: SCLD golden is in `ns`) |

See [`input/README.md`](../input/README.md) for the same notes next to the data.

---

## 4. Launch

The tool is a single Tkinter process — no server, no port. It displays over
X11 / Exceed like a terminal.

```bash
# From the repo root, on a host whose Python has Tkinter:
python -m cert_data_process.app                 # reads ./certi_runs
python -m cert_data_process.app --runs-dir /path/to/runs   # custom runs root
```

If you see `ERROR: this Python has no Tkinter`, select a Python built with Tk
(most EDA host Pythons have it; a stock `python3` usually works).

---

## 5. The tabs at a glance

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

## 6. Step-by-step: certifying your library

### 6.1 Setup — describe and launch the run

Open the **Setup** tab and fill in:

| Field | Notes |
|-------|-------|
| **Vendor** | `cdns` or `snps` (sets the default lib unit) |
| **Process / version** | e.g. `n2p` / `v1p0` |
| **Corners** | add each corner; or pull from History |
| **Timing types** | delay / slew / hold / mpw |
| **VT / RC type, Library type** | metadata for the run record |
| **FMC unit / Lib unit** | inputs are converted to ps internally; defaults track vendor/format |
| **abs_tol ps (hold)** | Waiver_2. One value for all corners, or `c1=19.5, c2=20`. **Blank = off.** If you type something unparseable, the tool *warns* instead of silently disabling W2. |
| **FMC input** | Decks (parse) / Parsed DFDS / Parsed SCLD — the FMC-dir label updates to match |
| **FMC dir / Lib dir** | **Browse** to your `input/fmc` and `input/lib` directories |

Click **▶ Run certification**. Moments (meanshift / std / skew) are derived from
the FMC data — no separate Full-MC run is needed.

![Setup tab](images/01_setup.png)

### 6.2 Pipeline — watch the run progress

The **Pipeline** tab streams each stage as it runs and surfaces any per-stage
audit findings. Wait for the run to finish; results then land in **Results**.

![Pipeline tab](images/02_pipeline.png)

### 6.3 Results — the verdict, and how waivers move it

The **Results** tab groups PR by timing type (delay / slew / hold). Cells are
green ≥95%, amber 90–95%, red <95%. Toggle the **basis** radios at the top to see
how each waiver changes the verdict:

| Basis | Meaning |
|-------|---------|
| **Base** | raw pass rate, no waivers |
| **+Waiver1** (CI +6%) | CI bounds enlarged 6% |
| **+Waiver2** (abs_tol) | your supplied `abs_tol` (ps), hold Late_Sigma only, stacked on Base+W1 |

This is the core story: a library that fails raw can certify once the agreed
waivers are applied — and the tool shows exactly which arcs each waiver rescued.

![Results tab](images/03_results.png)

### 6.4 PR Status — consolidated pivot

**PR Status → Build.** Rows are data-types (`ocv_const_hold`, `ocv_delay_late`,
…); columns are each batch × corner. Switch basis to see waivers applied across
every corner at once.

![PR Status tab](images/04_pr_status.png)

### 6.5 Outliers — what's actually failing

**Outliers → Build** (try the **Base** basis to see the most points). Each row is
a sub-95% (metric, corner) with its failure breakdown: `#cells`, `#opt`
(optimistic = Lib<MC, i.e. the library claims *better* than silicon), `#pess`,
polarity, and worst error.

> A `?` in a breakdown column means the per-arc CSV for that corner/type wasn't
> found (not a failure — just no detail to expand). The hint line under the table
> explains this.

![Outliers tab](images/05_outliers.png)

### 6.6 Outlier scatter + source trace-back — the cross-check

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

![Outlier drill-down](images/06_outlier_drill.png)

> If `matplotlib` isn't installed, the scatter degrades to a built-in Canvas plot
> — the rankings and source trace-back work either way.

### 6.7 Common offenders — systematic vs one-off

**Common** finds cells/arcs that fail across *multiple* contexts (corners/batches),
grouped by cell, cell+arc, or cell+table-point. Select several batches in History
first to compare recipes. Double-click an offender to see every place it fails.

![Common offenders tab](images/07_common.png)

### 6.8 History — managing and scoping runs

**History** lists every past run. Double-click a row to load it into **Results**;
▢-check several rows to scope **PR Status**, **Outliers**, and **Common** to just
those batches.

![History tab](images/08_history.png)

---

## 7. Waivers — terminology

- **Base PR** — raw pass rate, no waivers.
- **Waiver1** — CI bounds enlarged 6% (the engine's `Waiver1_CI_Enlarged`).
- **Waiver2** — `abs_tol` (ps), **hold Late_Sigma only**, stacked on Base+W1; you
  supply the value. The tool never invents it.

(Waiver3 is handled downstream by the separate Voltage-Margin tool and is out of
scope here.)

> Note the scope: "Waiver1 / Waiver2" above are the **in-tool** implementation
> columns. In the broader cert flow, everything this tool produces (Base + both
> in-tool waivers) is what the wider process calls `waiver_1`; the
> process-level `waiver_2` (`abs_tol` supplied by you) and `waiver_3` (Voltage
> Margin) are separate stages.

---

## 8. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ERROR: this Python has no Tkinter` | Use a Python built with Tk: `python -c "import tkinter"` should succeed. Most EDA host Pythons qualify. |
| Run fails immediately on a real deck | Confirm pandas/numpy are importable, and for lib-join that the EDA `ldbx` module is on `PYTHONPATH`. |
| Outlier breakdown columns show `?` | The per-arc CSV for that corner/type wasn't found — there's no detail to expand, but it's not a failure. |
| Scatter looks basic (no matplotlib styling) | `matplotlib` isn't installed; the Canvas fallback is in use. `pip install matplotlib` for the richer view. |
| Waiver2 seems ignored | Check the **abs_tol ps (hold)** field — blank means off; an unparseable value now raises a warning. |

---

*Headless / scripted runs:* a command-line pipeline also exists for batch use —
`python -m cert_data_process.cli --help`.
