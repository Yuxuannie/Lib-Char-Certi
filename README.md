# cert_data_process (Lib-Char-Certi)

`cert_data_process` is the **standard-cell library characterization certification**
tool. It validates a characterized library against Monte-Carlo / FMC reference
data, producing pass-rate (PR) tables, per-corner data-health flags, and an
outlier drill-down that traces any failing point back to its source `.lib` cell
and FMC input row.

The primary surface is a single-process **desktop console** (Tkinter, no
server/port) that runs over X11 / Exceed.

## Quick start

```bash
# Try it with bundled synthetic data — no inputs needed:
python -m cert_data_process.app --demo

# Real run (reads ./certi_runs):
python -m cert_data_process.app
```

If your Python lacks Tkinter, install/select one built with Tk (most EDA host
Pythons have it).

See **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)** for the full walkthrough
(setup → run → results → outlier cross-check).

## What it produces

- **Base PR** and **Waiver1** (CI +6%) pass-rate tables for sigma and moments
- **Waiver2** (`abs_tol`, hold-only, user-supplied) interactive recompute
- Consolidated PR pivot across batches/corners, with Data-Health flags
- Outlier breakdown + Lib-vs-MC scatter + source-file trace-back

## Optional dependency

`matplotlib` powers the enriched outlier scatter. It is **optional** — without it
the GUI falls back to a built-in Canvas scatter. Install it for the richer view:

```bash
pip install -e ".[plots]"     # or just: pip install matplotlib
```

## Command-line pipeline

A headless CLI also exists for batch/scripted runs:

```bash
python -m cert_data_process.cli --help
```

## Running tests

```bash
pytest tests/
# In EDA environments without PyPI access:
PYTHONPATH=. pytest tests/
```
