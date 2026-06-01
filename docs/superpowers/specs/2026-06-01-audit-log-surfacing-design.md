# Design Spec — Pipeline Audit (live log surfacing)

**Date:** 2026-06-01
**Status:** APPROVED (brainstorming) — ready for implementation plan
**Author:** Claude (superpowers brainstorming)

---

## 0. Problem

Today the Pipeline log window only echoes coarse stage state (`FMC Combine: running → passed`). The signals that actually matter — a stage that "passed" while the lib covered 4% of arcs, a corner with no matching lib, a liberate non-zero exit, an empty sigma table — are buried in per-stage log files / terminal output that the user must grep **after** the run. The audit feature surfaces those high-signal findings **into the log window as each stage finishes**, plus a persisted report and a summary banner.

## 1. Scope (decisions locked in brainstorming)

- **What to surface (B):** errors/failures **and** data-health risks (`NO_DATA`, `LOW_COVERAGE`, uncovered counts, `partial`). Not routine info.
- **When / granularity (A):** at **each stage's completion** (no mid-stage streaming — heavy stages are subprocesses), as **one grouped, severity-tagged block per stage**, capped to the top 6 with `+k more → <pointer>`.
- **Persistence (B):** a consolidated **`audit_report.txt`** per run **and** a **summary banner** on the Pipeline tab (`Audit: N errors · M warnings`, colored by worst severity).
- **Mechanism (Approach 3, hybrid):** one `auditor` that reads findings **structurally** from native stage results and **pattern-scans** subprocess stdout/log for the legacy health signals.

## 2. Architecture

New module **`cert_data_process/audit.py`** — the single definition of "what's worth surfacing." Pure and testable; no Tk, no subprocess.

### 2.1 `Finding`
```python
@dataclass(frozen=True)
class Finding:
    severity: str        # "error" | "warn"
    stage: str           # e.g. "lib_join_sigma"
    code: str            # snake_case, e.g. "low_coverage"
    message: str         # one-line, human-facing
    detail: str = ""     # optional extra context
    pointer: str = ""    # optional path to the full log/detail file
```

### 2.2 `audit_stage(stage_execution: dict, log_text: str) -> list[Finding]`
Two halves, merged into one list (structured first, then patterns; de-duplicated by `(code, message)`):

**Structured half** — from the stage dict the native stages already return:
- `status == "failed"` → `error` `stage_failed` (`reason`).
- `status == "partial"` → `warn` `partial` (`"<processed>/<processed+failures> succeeded"`).
- each item in `failures[]` → one finding; severity from `_REASON_SEVERITY` (below), message from `reason` + `detail`, `pointer` = stage `log_file`.

**Pattern half** — `PATTERNS`, a list of `(compiled_regex, severity, code, message_template)` scanned over `log_text`. Initial table:

| regex (gist) | severity | code | message |
|---|---|---|---|
| `DATA_HEALTH=NO_DATA` … `0/(\d+)` | error | `no_data` | `NO_DATA: lib covers 0/{total} arcs` |
| `DATA_HEALTH=LOW_COVERAGE` … `(\d+)/(\d+) \(([\d.]+)%\)` | warn | `low_coverage` | `LOW_COVERAGE {cov}/{total} ({pct}%)` |
| `(\d+)/(\d+) golden arcs NOT covered` | warn | `uncovered_arcs` | `{n}/{total} arcs uncovered by lib` |
| `reason=no_lib_for_corner` / `no_lib_for_type` | error | `no_lib` | `{reason}: {corner}` |
| `EXIT: (?!0)(-?\d+)` or `liberate exited with (\d+)` | error | `liberate_exit` | `liberate exit {code}` |
| `EMPTY sigma-table lookup=([1-9]\d*)` | warn | `sigma_table_empty` | `{k} matched arcs had no sigma table` |

`pointer` for pattern findings = the stage `log_file` (or the specific detail file when the pattern names one, e.g. `*_sigma_table_debug.txt`). The table is the **one place** to extend later (e.g. Special-Note hard-rule outliers).

### 2.3 Helpers
- `summarize(findings) -> {"errors": int, "warns": int, "by_stage": {stage: (e, w)}}` — banner data.
- `format_block(stage, findings, cap=6) -> list[tuple[str, str]]` — `(line_text, tag)` where tag ∈ `{"err","warn","ok"}`; emits a header line, up to `cap` bullets, then `+k more → <pointer>` if truncated. A stage with **no** findings yields a single `ok` line (`✓ {stage} — clean`).
- `write_report(findings, path)` — severity-sorted (errors first), grouped by stage, plain text. Overwrites per run.

### 2.4 Severity mapping (`_REASON_SEVERITY`)
- **error:** `no_lib_for_corner`, `no_lib_for_type`, `lib_join_failed`, `liberate_exit`, `no_data`, `bad_header`, `missing_input_dir`, `unrecognized_corner`, `unknown_type`.
- **warn:** `partial`, `low_coverage`, `uncovered_arcs`, `sigma_table_empty`, `no_rows_for_type`, `no_scld_file`, `no_parsed_file`.
- Unknown reason → default `warn`.

## 3. Data flow & orchestration

In **`cli.py:execute_stages`** (shared by CLI + GUI executor):
1. After each `_done(result)`: read `result.stage_execution["log_file"]` text (best-effort; empty string if absent), call `findings = audit.audit_stage(result.stage_execution, log_text)`, extend a run-level `all_findings`, and fire `on_finding(stage_name, findings)` if a callback was supplied.
2. The native stages already write their stdout/health lines into their `log_file`. For the subprocess PR stages (`get_pr_sigma`, `get_pr_moments`), ensure the stage result's `log_file` points at a file that captured the script's stdout/log (the scripts already emit `DATA_HEALTH=` lines) — if a stage has no single log file, the auditor still gets the structured half.
3. At the end: `audit.write_report(all_findings, output_dir/logs/audit_report.txt)` and store `audit_summary = summarize(all_findings)` in `run_manifest.json`.

`execute_stages` signature gains an optional `on_finding=None` alongside the existing `on_stage=None`. CLI passes `None` (it already prints stage lines); the GUI passes a callback.

**`web/executor.py`:** the JobManager worker forwards `on_finding` events through the same queue it already uses for `on_stage`, tagged so the GUI can route them.

**`app/gui.py`:**
- `_render_finding_block(stage, findings)` — calls `audit.format_block`, writes each `(text, tag)` to the existing `log_text` (tags `err`/`warn`/`ok` already configured).
- Audit banner: a `tk.Label` at the top of the Pipeline tab; a running `self._audit_counts` updated as findings arrive; text `Audit: {e} errors · {w} warnings`, bg green if 0/0, amber if warns only, red if any error. Reset on new run.
- The post-run `_surface_failures` (manifest scan → `failures_summary.txt`) is superseded by live findings + `audit_report.txt`; keep it only if it adds the file-write, otherwise remove to avoid duplication.

## 4. Error handling & robustness
- `audit_stage` is wrapped so it **never raises into the pipeline**: the pattern scan is in `try`; on any exception it returns the structured-half findings plus one `warn` `audit_error` finding. A missing/unreadable `log_file` → structured-half only.
- Window blocks cap at 6 bullets (`+k more → pointer`); `audit_report.txt` contains all findings.
- De-dupe by `(code, message)` so a signal in both the structured dict and the log text appears once.

## 5. Testing
- **`tests/test_audit.py`** (pure):
  - structured half: `failed`/`partial`/`passed` stage dicts + `failures[]` → expected findings & severities.
  - pattern half: synthetic `log_text` with each `PATTERNS` line → expected `(severity, code, message)`; non-zero vs zero `EXIT`; `LOW_COVERAGE 2780/66470 (4.2%)` parses cov/total/pct.
  - `summarize` counts; `format_block` capping + `ok` line for clean stage; `write_report` ordering; de-dupe.
  - `audit_stage` never raises on malformed input.
- **GUI smoke (extend `test_app_smoke.py`):** under mocked Tk, call `_render_finding_block` with sample findings and update the banner — catches construction/name errors.

## 6. Out of scope (YAGNI)
- Mid-stage live streaming (subprocess constraint; surface at completion).
- User-configurable severity/patterns.
- Special-Note hard-rule outlier signals (`nom − 3·early_ocv > 0`, nominal 0.5% sanity) — deliberately deferred; adding them is a new `PATTERNS`/structured entry later.

## 7. Self-review notes
- Placeholders: none; the `PATTERNS` table lists concrete signals (more can be appended without design change).
- Consistency: one `Finding` type flows from `audit_stage` → `format_block`/`write_report`/`summarize` → window/file/banner; severity tags reuse the existing `err`/`warn`/`ok` log tags.
- Scope: single module + thin glue in 3 existing files; testable in isolation; not a multi-subsystem effort.
- Ambiguity: `NO_DATA` classified **error** (a metric with zero data is a real problem), `LOW_COVERAGE` **warn** — stated explicitly in §2.4.
