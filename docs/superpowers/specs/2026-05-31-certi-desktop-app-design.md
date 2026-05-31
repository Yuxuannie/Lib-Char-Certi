# CERTI Desktop App (Tkinter) — Design

Date: 2026-05-31
Status: approved (user: "tkinter is available, please rewrite immediately").

## Problem
The browser console requires the browser and the stdlib HTTP server to be on the
same host. In the user's Exceed/VDI environment, terminals and Firefox land on
different nodes unpredictably, so `localhost` fails and hardcoding hostnames is
fragile and cumbersome. Root cause: browser and server are two processes that may
live on two hosts.

## Solution
A single-process **Tkinter desktop app**: one process draws the window and runs
the pipeline. No HTTP, no port, no localhost, no host-matching. Displays over
X11/Exceed like the terminal. Tkinter is in the host's Python (confirmed).

## Architecture (only the view is new)
- New package `cert_data_process/app/`: `gui.py` (Tk window), `__main__.py`
  (entry: `python -m cert_data_process.app`).
- Reused unchanged:
  - `config.build_config` — config validation.
  - `cli.execute_stages(config, on_stage)` — the pipeline.
  - `web/runs.py` — runs store + history index (`read_index`, `read_run_record`).
  - `web/executor.JobManager` — UI-agnostic: threads, N concurrent batches, global
    liberate budget, writes run records + index. The app submits to it and polls
    `manager.status(id)` via `root.after()` (Tk is not thread-safe; never touch
    widgets from worker threads).

## UI (ttk.Notebook tabs — same flow as the web console)
- **Setup**: vendor radio; process/version entries; editable corner list
  (Listbox + add field + remove + history-derived suggestions); type checkboxes
  delay/slew/hold/**mpw**; FMC/lib dir entries with `filedialog` browse; Run button.
- **Pipeline**: live 5-stage status (fmc_combine, lib_join, build_pr, moments,
  dashboard) with colored states; updated by polling JobManager.status.
- **Results**: sigma + moments tables (`ttk.Treeview`) with coverage and
  color-coded Data_Health (OK/LOW_COVERAGE/NO_DATA).
- **History**: all batches from index.json; open one → Results.
- **Compare**: multi-select batches → late-sigma Base_PR side by side.

## Data flow
Setup → `manager.submit(cfg)` (validates, enqueues) → switch to Pipeline →
`root.after(~800ms)` polls `manager.status(id)` → on terminal state, refresh
History + load Results from `run_record.json`.

## Error handling
- JobManager already catches job exceptions and writes a `failed` record.
- Setup validation errors (ValueError from build_config, surfaced by submit) →
  `messagebox.showerror`.
- Tk-safety: all widget updates happen on the main thread via after-polling.

## Testing
- Pure logic (JobManager, runs, summary) already covered / integration-tested.
- GUI requires `$DISPLAY`; cannot run on the dev box. Keep pure helpers
  display-free; verify `import tkinter` and that importing `app.gui` opens no
  window. Backend correctness relies on existing tests.

## Out of scope
Browser server (kept, harmless, single-host option). Analysis page / Voltage
Margin (future). G7 step 2.
