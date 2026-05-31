# CERTI Console — Architecture & P1 Design

Date: 2026-05-31
Status: approved (overall architecture); P1 detailed for implementation.

## 1. Goal

Turn Lib-Char-Certi into a complete-flow, user-friendly product: a local browser
console where the engineer configures a certification batch, launches it, watches
live stage progress, and views/compares results and history across many recipes —
plus a pluggable Analysis page (first tool: Voltage Margin).

## 2. Constraints (decisive)

- **Air-gapped EDA host**: no internet, no npm/CDN, no pip. Backend = Python
  **stdlib only** (`http.server`, `json`, `threading`, `concurrent.futures`,
  `sqlite3` not used). Frontend = single self-contained HTML (system fonts, inline
  CSS/JS), the existing `gui/certi_console.html`.
- **RAM-tight host** (many cores, low free memory). `liberate` is memory-heavy.
- Single user, localhost only (`127.0.0.1:<port>`), no auth.
- Reuse the existing pipeline stage functions; do not duplicate pipeline logic.

## 3. Architecture (north star)

New stdlib package `cert_data_process/web/`:

- `runs.py` — runs store: runs root, per-batch dir, `run_record.json`, `index.json`.
- `server.py` — `http.server` app: serves the console + JSON API.
- `executor.py` — job manager: N-concurrent batch workers + a **global liberate
  budget** (process-wide semaphore) so total liberate processes across all batches
  is hard-capped regardless of batch concurrency. This is the key RAM safety piece.

The console (frontend) fetches from the API; keeps embedded DEMO data as a
standalone-file fallback.

### Data seam
`CERTI_DATA` (already defined) is the contract. `/api/batch/{id}` returns one
batch in that shape; `/api/history` returns the lightweight index.

### API (JSON; live progress via polling, no WebSocket/SSE)
| Endpoint | Purpose |
|---|---|
| `GET /` | console HTML + injected bootstrap (concurrency cap, runs root) |
| `GET /api/history` | `index.json` — batches: id, name, when, status, score, worst health |
| `GET /api/batch/{id}` | batch `CERTI_DATA` (config, stages, sigma, moments) |
| `POST /api/run` | submit config → `{id}`, enqueued |
| `GET /api/status/{id}` | live: queued\|running\|partial\|passed\|failed + per-stage state |
| `GET /api/analysis/{tool}` | (P4) analysis-tool data endpoints |

### Concurrency
- Batch concurrency: configurable (default 2) — a bounded worker pool of batch jobs.
- Global liberate budget: configurable (default 4) — a process-wide semaphore every
  lib_join liberate launch acquires, across all batches. `lib_join_sigma` accepts an
  injected limiter (falls back to its own `CERTI_LIB_JOIN_WORKERS` pool when run
  standalone via CLI).

### Analysis page (reserved; built in P4)
A top-level **Analysis** console section hosting pluggable tools behind a seam:
frontend registry `{id, name, render(container, batchContext)}` + optional
`/api/analysis/{tool}` endpoints. First plugins: **Voltage Margin** (consumes a
batch's lib-join output; downstream tool handling waiver_3) and the **optimistic
analysis** deferred from G1. Nav slot + empty registry reserved in P2.

## 4. Decomposition (each = own spec → plan → implementation)

- **P1 — Runs store + history index** (this doc): file-based store, `run_record.json`,
  `index.json`, and CLI emission of records so runs persist. Delivers G6 standalone.
- **P2 — Control server (read-only)**: serve console + `/api/history` + `/api/batch`
  over the store; frontend fetches from API; reserve Analysis nav + registry.
- **P3 — Executor + launch-from-GUI**: `POST /api/run`, `/api/status`, live Pipeline
  polling, N-concurrent batches + global liberate budget.
- **P4 — Analysis page + plugin framework + Voltage Margin integration**.

## 5. P1 — Detailed design (implement first)

### 5.1 Purpose
Persist every run as an inspectable record and maintain a history index, so the
console (P2) and Compare have real data, and runs accumulate across recipes.

### 5.2 Module: `cert_data_process/web/runs.py` (pure, stdlib, no server)

Functions (well-bounded, independently testable):

- `runs_root(config_or_path) -> Path` — resolve runs root (default `./certi_runs/`,
  override via `--runs-dir` / `CERTI_RUNS_DIR`).
- `batch_id(name: str, timestamp: str) -> str` — `slug(name)_YYYYmmdd_HHMMSS`.
- `write_run_record(runs_root, batch_id, record: dict) -> Path` — atomic write of
  `runs_root/{batch_id}/run_record.json` (temp file + `os.replace`).
- `update_index(runs_root, summary: dict) -> None` — atomic upsert of one batch
  summary into `runs_root/index.json` (read-modify-write under a file lock; last
  write wins per batch_id).
- `read_index(runs_root) -> list[dict]` — sorted by `when` desc; tolerant of a
  missing/corrupt index (returns []).
- `read_run_record(runs_root, batch_id) -> dict | None`.

### 5.3 `run_record.json` schema (one batch)
```
{
  "schema_version": 1,
  "id": "n2p_v0p9_cdns_20260531_125200",
  "name": "N2P v0.9 · CDNS · Best",
  "when_utc": "2026-05-31T12:52:00Z",
  "config": {vendor, process, process_version, corners[], types[],
             fmc_golden_dir, lib_dir, output_dir},
  "status": "passed|partial|failed|skipped",
  "stages": [{stage, status, pipeline, reason}],     // from stage_execution
  "sigma":  [ ... CERTI_DATA sigma rows ... ],        // parsed from pr/sigma table
  "moments":[ ... CERTI_DATA moments rows ... ]       // parsed from pr/moments table
}
```
`sigma`/`moments` rows reuse the exact shape `pr_web_app` already builds
(`_sigma_rows`/`_moments_rows`) — factored into a shared builder so the record and
the dashboard agree.

### 5.4 `index.json` schema (history list)
```
[ { "id", "name", "when_utc", "vendor", "process", "version",
    "status", "mean_late_sigma", "worst_health" }, ... ]
```
`mean_late_sigma` and `worst_health` are summary fields for the History tiles.

### 5.5 Integration with the CLI run
- `cli.py` gains `--runs-dir` (default `./certi_runs/`) and `--batch-name`
  (default derived from `process/version/vendor`).
- After stages complete, the run writes its full output tree **into the batch dir**
  under runs root (`runs_root/{batch_id}/`), emits `run_record.json`, and upserts
  `index.json`. (Output-dir behavior: `--output-dir` still honored; when `--runs-dir`
  is used, the batch dir is the output dir. Default keeps current behavior if
  `--runs-dir` unset — back-compat.)
- Refactor: extract the sigma/moments row builders from `pr_web_app` into a shared
  helper (`web/summary.py` or `pr_web_app` exports) used by both the record writer
  and the dashboard.

### 5.6 Error handling
- Missing/corrupt `index.json` → treated as empty, rebuilt on next upsert (warn in log).
- Atomic writes (`tempfile` + `os.replace`) so a crash mid-write can't corrupt the
  index; a coarse file lock (or a single-writer assumption for CLI; the server in P3
  serializes index writes via the executor) prevents interleaved writes.
- A run that fails mid-pipeline still emits a record with `status` and partial
  sigma/moments + Data_Health (honest, consistent with G2).

### 5.7 Testing (pytest, stdlib, no liberate)
- `runs.py` units: id slugging, atomic write, index upsert/read, corrupt-index
  tolerance, sort order.
- Record build: given a fake output dir with pr tables → record sigma/moments match
  the dashboard builder output.
- CLI integration: a dummy run (monkeypatched stages) with `--runs-dir` produces a
  batch dir + `run_record.json` + an `index.json` entry; a second run appends.

## 6. Out of scope for P1
Server, executor, live progress, launching from GUI (P2/P3), Analysis tools (P4).

## 7. Open questions (later phases)
- Voltage Margin's exact handoff/interface (P4) — depends on the VM tool.
- Port/host config and how the user opens the browser on the EDA host (P2).
- Whether History should prune/cap old runs (P2+).
