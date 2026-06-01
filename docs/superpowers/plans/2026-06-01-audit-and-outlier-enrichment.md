# Pipeline Audit + Outlier Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface high-signal pipeline findings into the live log window (Part A) and turn the outlier drill-down into a ranked, professional-plot analysis panel that helps the user converge (Part B).

**Architecture:** A pure `cert_data_process/audit.py` extracts `Finding`s from each stage (structured `failures[]` + a `PATTERNS` scan of the stage's captured log). `execute_stages` runs the auditor per stage and feeds findings through the **existing status-polling path** (JobManager accumulates them in batch status; the GUI `_poll` drains and renders them + a banner), and writes `audit_report.txt`. Part B adds pure ranking functions to `outliers.py`, a matplotlib figure builder in `analysis/plots.py` (no pyplot, so it tests headless via Agg and embeds in Tk via `FigureCanvasTkAgg`), and an enriched detail panel.

**Tech Stack:** Python 3.9+, stdlib (`audit.py`, ranking), matplotlib (plots; host-present, guarded import + Canvas fallback), Tkinter, pytest.

**Host note (manual file copy):** group commits so the engineer can copy whole files. New files: `cert_data_process/audit.py`, `cert_data_process/analysis/plots.py`. Modified: `cli.py`, `web/executor.py`, `app/gui.py`, `analysis/outliers.py`. After execution, the final message must list these exact paths to copy.

---

## File structure

| File | Responsibility |
|------|----------------|
| `cert_data_process/audit.py` (new) | `Finding`, `audit_stage`, `PATTERNS`, `summarize`, `format_block`, `write_report`, `findings_to_dicts` |
| `cert_data_process/cli.py` (mod) | `execute_stages(..., on_finding=None)`: per-stage audit, accumulate, write report, manifest summary |
| `cert_data_process/web/executor.py` (mod) | accumulate findings into batch status for the GUI poll to drain |
| `cert_data_process/app/gui.py` (mod) | render new findings in log window + audit banner; enriched outlier detail panel |
| `cert_data_process/analysis/outliers.py` (mod) | `arc_indices`, `rank_by_cell`, `rank_by_table_point`, `worst_arcs` |
| `cert_data_process/analysis/plots.py` (new) | `metric_unit`, `build_scatter_figure`, `save_figure` |

---

# PART A — Pipeline Audit

## Task A1: `Finding` + structured-half `audit_stage`

**Files:** Create `cert_data_process/audit.py`; Test `tests/test_audit.py`

- [ ] **Step 1: failing test**
```python
# tests/test_audit.py
from cert_data_process.audit import Finding, audit_stage

def test_failed_stage_yields_error():
    se = {"stage": "lib_join_sigma", "status": "failed", "reason": "no_lib_inputs",
          "failures": [], "log_file": "/x.log"}
    f = audit_stage(se, "")
    assert any(x.severity == "error" and x.code == "stage_failed" for x in f)

def test_partial_and_failures_list():
    se = {"stage": "fmc_combine_data", "status": "partial",
          "processed": [1, 2], "failures": [
              {"reason": "no_scld_file", "detail": "corner X", "corner": "X"}],
          "log_file": "/x.log"}
    f = audit_stage(se, "")
    codes = {x.code for x in f}
    assert "partial" in codes              # warn
    assert "no_scld_file" in codes         # warn (from _REASON_SEVERITY)
    nl = next(x for x in f if x.code == "no_scld_file")
    assert nl.severity == "warn" and nl.pointer == "/x.log"
```
- [ ] **Step 2: run, expect fail** — `PYTHONPATH=. python -m pytest tests/test_audit.py -q` → ModuleNotFoundError.
- [ ] **Step 3: implement structured half**
```python
# cert_data_process/audit.py
"""Pipeline audit: extract high-signal Findings from each stage (structured stage
dict + a pattern scan of the stage's captured log) and render them to the log
window / report / banner. Pure: no Tk, no subprocess."""
from __future__ import annotations
import re
from dataclasses import dataclass, asdict
from typing import Any

@dataclass(frozen=True)
class Finding:
    severity: str        # "error" | "warn"
    stage: str
    code: str
    message: str
    detail: str = ""
    pointer: str = ""
    def to_dict(self) -> dict:
        return asdict(self)

_REASON_SEVERITY = {
    "no_lib_for_corner": "error", "no_lib_for_type": "error", "lib_join_failed": "error",
    "liberate_exit": "error", "no_data": "error", "bad_header": "error",
    "missing_input_dir": "error", "unrecognized_corner": "error", "unknown_type": "error",
    "partial": "warn", "low_coverage": "warn", "uncovered_arcs": "warn",
    "sigma_table_empty": "warn", "no_rows_for_type": "warn", "no_scld_file": "warn",
    "no_parsed_file": "warn",
}

def _sev(code: str) -> str:
    return _REASON_SEVERITY.get(code, "warn")

def _structured(se: dict) -> list:
    stage = se.get("stage", "?")
    ptr = se.get("log_file", "") or ""
    out = []
    status = se.get("status", "")
    if status == "failed":
        out.append(Finding("error", stage, "stage_failed", f"{stage} failed",
                           se.get("reason", ""), ptr))
    elif status == "partial":
        n_ok = len(se.get("processed", []) or [])
        n_fail = len(se.get("failures", []) or [])
        out.append(Finding("warn", stage, "partial",
                           f"{stage} partial — {n_ok}/{n_ok + n_fail} succeeded", "", ptr))
    for fa in se.get("failures", []) or []:
        code = fa.get("reason", "failure")
        msg = code + (f": {fa.get('corner')}" if fa.get("corner") else "")
        out.append(Finding(_sev(code), stage, code, msg, fa.get("detail", ""), ptr))
    return out

def audit_stage(stage_execution: dict, log_text: str) -> list:
    findings = _structured(stage_execution)
    # pattern half added in Task A2
    seen = set(); uniq = []
    for f in findings:
        k = (f.code, f.message)
        if k not in seen:
            seen.add(k); uniq.append(f)
    return uniq
```
- [ ] **Step 4: run, expect pass.**
- [ ] **Step 5: commit** — `git add cert_data_process/audit.py tests/test_audit.py && git commit -m "feat: audit Finding + structured-half audit_stage"`

## Task A2: `PATTERNS` scan (subprocess health signals)

**Files:** Modify `cert_data_process/audit.py`; Test `tests/test_audit.py`

- [ ] **Step 1: failing test**
```python
def test_patterns_low_coverage_and_no_data():
    log = ("DATA_HEALTH=LOW_COVERAGE: lib covers only 2780/66470 (4.2%) delay arcs\n"
           "DATA_HEALTH=NO_DATA: lib covers 0/120 hold arcs\n")
    f = {x.code: x for x in audit_stage({"stage": "build_pr_table", "status": "passed",
                                         "failures": [], "log_file": "/l"}, log)}
    assert f["low_coverage"].severity == "warn" and "2780/66470" in f["low_coverage"].message
    assert f["no_data"].severity == "error" and "0/120" in f["no_data"].message

def test_patterns_liberate_exit_and_sigma_empty():
    log = "EXIT: 1\nSigma-table diagnostic: x | matched arcs sampled=40 | with EMPTY sigma-table lookup=12\n"
    codes = {x.code for x in audit_stage({"stage": "lib_join_sigma", "status": "passed",
                                          "failures": [], "log_file": "/l"}, log)}
    assert "liberate_exit" in codes and "sigma_table_empty" in codes

def test_patterns_exit_zero_is_not_a_finding():
    codes = {x.code for x in audit_stage({"stage": "lib_join_sigma", "status": "passed",
                                          "failures": [], "log_file": "/l"}, "EXIT: 0\n")}
    assert "liberate_exit" not in codes
```
- [ ] **Step 2: run, expect fail** (KeyError / missing codes).
- [ ] **Step 3: implement PATTERNS + scan.** Add to `audit.py`:
```python
# (compiled regex, severity, code, message builder taking the match)
PATTERNS = [
    (re.compile(r"DATA_HEALTH=NO_DATA.*?0/(\d+)"), "error", "no_data",
     lambda m: f"NO_DATA: lib covers 0/{m.group(1)} arcs"),
    (re.compile(r"DATA_HEALTH=LOW_COVERAGE.*?(\d+)/(\d+)\s*\(([\d.]+)%\)"), "warn", "low_coverage",
     lambda m: f"LOW_COVERAGE {m.group(1)}/{m.group(2)} ({m.group(3)}%)"),
    (re.compile(r"(\d+)/(\d+)\s+golden arcs NOT covered"), "warn", "uncovered_arcs",
     lambda m: f"{m.group(1)}/{m.group(2)} arcs uncovered by lib"),
    (re.compile(r"\bEXIT:\s*(-?[1-9]\d*)\b"), "error", "liberate_exit",
     lambda m: f"liberate exit {m.group(1)}"),
    (re.compile(r"liberate exited with (\d+)"), "error", "liberate_exit",
     lambda m: f"liberate exit {m.group(1)}"),
    (re.compile(r"EMPTY sigma-table lookup=([1-9]\d*)"), "warn", "sigma_table_empty",
     lambda m: f"{m.group(1)} matched arcs had no sigma table"),
]

def _patterns(se: dict, log_text: str) -> list:
    stage = se.get("stage", "?"); ptr = se.get("log_file", "") or ""
    out = []
    if not log_text:
        return out
    try:
        for rx, sev, code, build in PATTERNS:
            m = rx.search(log_text)
            if m:
                out.append(Finding(sev, stage, code, build(m), "", ptr))
    except Exception as exc:  # never crash the run on a bad log
        out.append(Finding("warn", stage, "audit_error", f"audit scan error: {exc}", "", ptr))
    return out
```
Then in `audit_stage`, change `findings = _structured(stage_execution)` to:
```python
    findings = _structured(stage_execution) + _patterns(stage_execution, log_text)
```
- [ ] **Step 4: run, expect pass.**
- [ ] **Step 5: commit** — `git commit -am "feat: audit PATTERNS scan for subprocess health signals"`

## Task A3: `summarize` + `format_block` + `write_report` + `findings_to_dicts`

**Files:** Modify `cert_data_process/audit.py`; Test `tests/test_audit.py`

- [ ] **Step 1: failing test**
```python
from cert_data_process.audit import summarize, format_block, write_report, findings_to_dicts

def _f(sev, code, msg, ptr="/l"):
    from cert_data_process.audit import Finding
    return Finding(sev, "s", code, msg, "", ptr)

def test_summarize_counts():
    s = summarize(findings_to_dicts([_f("error","a","A"), _f("warn","b","B"), _f("warn","c","C")]))
    assert s["errors"] == 1 and s["warns"] == 2

def test_format_block_caps_and_clean():
    fs = findings_to_dicts([_f("warn", f"c{i}", f"m{i}") for i in range(8)])
    lines = format_block("lib_join_sigma", fs, cap=3)
    assert lines[0][1] == "warn"                       # header tagged by worst severity
    assert any("+5 more" in t for t, _ in lines)       # 8 - 3 = 5 capped
    clean = format_block("fmc_combine_data", [], cap=3)
    assert len(clean) == 1 and clean[0][1] == "ok"

def test_write_report(tmp_path):
    p = tmp_path / "audit_report.txt"
    write_report(findings_to_dicts([_f("error","a","Aerr"), _f("warn","b","Bwarn")]), p)
    txt = p.read_text()
    assert "Aerr" in txt and txt.index("Aerr") < txt.index("Bwarn")  # errors first
```
- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement.** Add to `audit.py`:
```python
def findings_to_dicts(findings) -> list:
    return [f.to_dict() if hasattr(f, "to_dict") else dict(f) for f in findings]

def summarize(finding_dicts: list) -> dict:
    errors = sum(1 for f in finding_dicts if f["severity"] == "error")
    warns = sum(1 for f in finding_dicts if f["severity"] == "warn")
    by_stage: dict = {}
    for f in finding_dicts:
        e, w = by_stage.get(f["stage"], (0, 0))
        by_stage[f["stage"]] = (e + (f["severity"] == "error"), w + (f["severity"] == "warn"))
    return {"errors": errors, "warns": warns, "by_stage": by_stage}

_ICON = {"error": "✖", "warn": "⚠"}  # ✖ ⚠

def format_block(stage: str, finding_dicts: list, cap: int = 6) -> list:
    if not finding_dicts:
        return [(f"✓ {stage} — clean", "ok")]
    worst = "err" if any(f["severity"] == "error" for f in finding_dicts) else "warn"
    n_err = sum(1 for f in finding_dicts if f["severity"] == "error")
    n_warn = len(finding_dicts) - n_err
    lines = [(f"{stage} — {n_err} error(s), {n_warn} warning(s)", worst)]
    shown = finding_dicts[:cap]
    for f in shown:
        tag = "err" if f["severity"] == "error" else "warn"
        msg = f"   {_ICON.get(f['severity'], '')} {f['message']}"
        if f.get("detail"):
            msg += f" — {f['detail']}"
        lines.append((msg, tag))
    extra = len(finding_dicts) - len(shown)
    if extra > 0:
        ptr = next((f.get("pointer") for f in finding_dicts if f.get("pointer")), "")
        lines.append((f"   +{extra} more → {ptr}", worst))
    return lines

def write_report(finding_dicts: list, path) -> None:
    from pathlib import Path
    order = {"error": 0, "warn": 1}
    ordered = sorted(finding_dicts, key=lambda f: (order.get(f["severity"], 2), f["stage"]))
    lines = ["AUDIT REPORT", "=" * 60, ""]
    for f in ordered:
        lines.append(f"[{f['severity'].upper()}] {f['stage']}: {f['message']}"
                     + (f" — {f['detail']}" if f.get("detail") else ""))
        if f.get("pointer"):
            lines.append(f"    see: {f['pointer']}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
```
- [ ] **Step 4: run, expect pass.**
- [ ] **Step 5: commit** — `git commit -am "feat: audit summarize/format_block/write_report"`

## Task A4: wire the auditor into `execute_stages`

**Files:** Modify `cert_data_process/cli.py` (the `execute_stages` function); Test: covered by A5/A6 integration + manual.

- [ ] **Step 1: add `on_finding` + audit calls.** In `cli.py`, change the signature `def execute_stages(config, on_stage=None):` to `def execute_stages(config, on_stage=None, on_finding=None):`. Add near the top of the function (after `from .audit import ...`):
```python
    from . import audit
    all_findings: list = []

    def _audit(result) -> None:
        se = result.stage_execution
        log_text = ""
        lf = se.get("log_file")
        if lf:
            try:
                from pathlib import Path as _P
                log_text = _P(lf).read_text(encoding="utf-8", errors="replace")
            except OSError:
                log_text = ""
        findings = audit.audit_stage(se, log_text)
        dicts = audit.findings_to_dicts(findings)
        all_findings.extend(dicts)
        if on_finding and dicts is not None:
            on_finding(se.get("stage", "?"), dicts)
```
In the existing `_done(result)` helper, after `failed = _record_stage(...) or failed`, add `_audit(result)`.
- [ ] **Step 2: write report + manifest summary at the end.** Just before `write_manifests(config, stage_execution, compatibility_stage_reports)`, add:
```python
    try:
        audit.write_report(all_findings, config.output_dir / "logs" / "audit_report.txt")
    except OSError:
        pass
```
And extend `write_manifests` (in the same file) to accept and store an `audit_summary`: add param `audit_summary=None` and `run_manifest["audit_summary"] = audit_summary or {}`. Pass `audit.summarize(all_findings)` from `execute_stages`.
- [ ] **Step 3: verify nothing breaks** — `PYTHONPATH=. python -m pytest tests/ -q` → all pass (existing CLI tests still green; CLI passes `on_finding=None`).
- [ ] **Step 4: commit** — `git commit -am "feat: run auditor per stage in execute_stages + write audit_report"`

## Task A4b: ensure PR stages expose an auditable log

**Files:** Modify `cert_data_process/stages/get_pr_sigma.py`, `cert_data_process/stages/get_pr_moments.py`

- [ ] **Step 1: check current capture** — `grep -n "log_file\|capture_output\|stdout\|\.log" cert_data_process/stages/get_pr_sigma.py`. The `DATA_HEALTH=LOW_COVERAGE`/`NO_DATA` lines are printed by `check_sigma_with_waivers.py`/`check_moments_from_fmc.py`.
- [ ] **Step 2:** If the subprocess stdout is NOT already written to a file referenced by `stage_execution["log_file"]`, capture it: run the subprocess with `capture_output=True, text=True`, write `proc.stdout + proc.stderr` to `output_dir/logs/<stage>.log`, and set `stage_execution["log_file"]` to that path. (If it already does, no change.) Keep the existing PR-table copy/print behavior intact.
- [ ] **Step 3: verify** — run the suite (`pytest tests/ -q`) green; if a fixture run is available, confirm `logs/build_pr_table.log` contains the `DATA_HEALTH` lines.
- [ ] **Step 4: commit** — `git commit -am "feat: capture PR-stage stdout to a log so the auditor can scan coverage signals"`

## Task A5: accumulate findings in JobManager status

**Files:** Modify `cert_data_process/web/executor.py`

- [ ] **Step 1:** In `submit`, add `"findings": []` to the initial `self._status[batch_id]` dict (next to `"stages"`).
- [ ] **Step 2:** In `status()` and `all_status()`, deep-copy findings too: change `dict(st, stages=dict(st["stages"]))` → `dict(st, stages=dict(st["stages"]), findings=list(st.get("findings", [])))`.
- [ ] **Step 3:** Add an accumulator method:
```python
    def _add_findings(self, batch_id: str, items: list) -> None:
        with self._lock:
            self._status[batch_id].setdefault("findings", []).extend(items)
```
- [ ] **Step 4:** In `_run`, define and pass `on_finding`:
```python
        def on_finding(stage: str, items: list) -> None:
            self._add_findings(batch_id, items)
        stage_execution, _compat, _failed = execute_stages(config, on_stage=on_stage, on_finding=on_finding)
```
- [ ] **Step 5: verify** — `PYTHONPATH=. python -m pytest tests/ -q` green.
- [ ] **Step 6: commit** — `git commit -am "feat: accumulate audit findings in JobManager batch status"`

## Task A6: render findings + audit banner in the GUI

**Files:** Modify `cert_data_process/app/gui.py`; Test `tests/test_app_smoke.py`

- [ ] **Step 1: add the audit banner** in `_build_pipeline` (after `self.pipe_banner` is packed):
```python
        self.audit_banner = tk.Label(f, text="", anchor="w", padx=10, pady=4,
                                     font=("DejaVu Sans", 10, "bold"))
        self.audit_banner.pack(fill="x", pady=(0, 6))
```
- [ ] **Step 2: reset audit state when a run starts.** In the submit/start path (where `pipe_banner` is set to "queued…"), add:
```python
        self._audit_shown = 0
        self.audit_banner.configure(text="", bg=self.palette["BG"])
```
- [ ] **Step 3: drain + render new findings in `_poll`.** After it reads `st = self.manager.status(self.active_job)`, add:
```python
        from .. import audit as _audit
        findings = st.get("findings", []) if st else []
        shown = getattr(self, "_audit_shown", 0)
        if len(findings) > shown:
            new = findings[shown:]
            by_stage: dict = {}
            for fnd in new:
                by_stage.setdefault(fnd["stage"], []).append(fnd)
            for stage, items in by_stage.items():
                for text, tag in _audit.format_block(stage, items, cap=6):
                    self._log(text, tag)
            self._audit_shown = len(findings)
            s = _audit.summarize(findings)
            bg = "#fad4d4" if s["errors"] else ("#fdebc8" if s["warns"] else "#d8f5e0")
            self.audit_banner.configure(text=f"Audit: {s['errors']} errors · {s['warns']} warnings", bg=bg)
```
- [ ] **Step 4: extend the smoke test** (`tests/test_app_smoke.py`, inside the existing render test):
```python
    # audit banner + finding rendering under mocked tk
    app._audit_shown = 0
    from cert_data_process import audit as _audit
    sample = _audit.findings_to_dicts(
        [_audit.Finding("error", "lib_join_sigma", "no_lib", "no_lib_for_corner: X", "", "/l"),
         _audit.Finding("warn", "build_pr_table", "low_coverage", "LOW_COVERAGE 2780/66470 (4.2%)", "", "/l")])
    for s, items in {"lib_join_sigma": sample[:1], "build_pr_table": sample[1:]}.items():
        for text, tag in _audit.format_block(s, items):
            app._log(text, tag)
```
- [ ] **Step 5: run** — `PYTHONPATH=. python -m pytest tests/test_app_smoke.py -q` → pass.
- [ ] **Step 6: commit** — `git commit -am "feat: render audit findings live in log window + Pipeline audit banner"`

---

# PART B — Outlier Analysis Enrichment

## Task B1: ranking functions in `outliers.py`

**Files:** Modify `cert_data_process/analysis/outliers.py`; Test `tests/test_outliers.py`

- [ ] **Step 1: failing test**
```python
from cert_data_process.analysis.outliers import arc_indices, rank_by_cell, rank_by_table_point, worst_arcs

def _a(cell, i1, i2, mc, lib, status):
    return {"Arc": f"combinational_{cell}_Z_rise_A_rise_NO_CONDITION_{i1}_{i2}",
            "Late_Sigma_MC_value": str(mc), "Late_Sigma_Lib_value": str(lib),
            "Late_Sigma_Final_Status": status}

def test_arc_indices():
    assert arc_indices("combinational_INV_Z_rise_A_rise_NO_CONDITION_3_5") == ("3", "5")
    assert arc_indices("weird") == ("", "")

def test_rank_by_cell_orders_by_failcount_then_worst():
    rows = [_a("A", 3, 5, 40, 38, "Fail"), _a("A", 3, 6, 40, 39, "Fail"),
            _a("B", 3, 5, 50, 70, "Fail"), _a("C", 1, 1, 10, 10, "Pass")]
    r = rank_by_cell(rows, "Late_Sigma")
    assert r[0]["cell"] == "A" and r[0]["n_fail"] == 2
    assert {x["cell"] for x in r} == {"A", "B"}        # C passed -> excluded
    assert r[1]["cell"] == "B" and round(r[1]["worst_rel_pct"], 0) == 40

def test_rank_by_table_point_and_worst_arcs():
    rows = [_a("A", 3, 5, 40, 38, "Fail"), _a("B", 3, 5, 50, 70, "Fail"),
            _a("C", 7, 7, 10, 10, "Pass")]
    tp = rank_by_table_point(rows, "Late_Sigma")
    assert tp[0]["index1"] == "3" and tp[0]["index2"] == "5" and tp[0]["n_fail"] == 2
    w = worst_arcs(rows, "Late_Sigma", top=5)
    assert w[0]["cell"] == "B" and w[0]["direction"] == "pessimistic" and round(w[0]["rel_pct"]) == 40
```
- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement.** Add to `outliers.py` (reuses existing `_f`, `_is_pass`, `_cell_of`):
```python
import re as _re

def arc_indices(arc: str):
    parts = str(arc).split("_")
    return (parts[-2], parts[-1]) if len(parts) >= 2 and _re.fullmatch(r"-?\d+", parts[-1] or "") else ("", "")

def _failing(rows, metric):
    mc_k, lib_k, st_k = f"{metric}_MC_value", f"{metric}_Lib_value", f"{metric}_Final_Status"
    for r in rows:
        if _is_pass(r.get(st_k, "")):
            continue
        mc, lib = _f(r.get(mc_k)), _f(r.get(lib_k))
        if mc is None or lib is None:
            continue
        rel = abs(lib - mc) / abs(mc) * 100.0 if mc != 0 else 0.0
        yield r, mc, lib, abs(lib - mc), rel

def rank_by_cell(rows, metric):
    agg = {}
    for r, mc, lib, ae, rel in _failing(rows, metric):
        c = _cell_of(r.get("Arc", ""))
        d = agg.setdefault(c, {"cell": c, "n_fail": 0, "worst_rel_pct": 0.0, "worst_err_ps": 0.0,
                               "n_opt": 0, "n_pess": 0})
        d["n_fail"] += 1
        d["worst_rel_pct"] = max(d["worst_rel_pct"], rel)
        d["worst_err_ps"] = max(d["worst_err_ps"], ae)
        d["n_opt" if lib < mc else "n_pess"] += 1
    for d in agg.values():
        d["polarity"] = ("mixed" if d["n_opt"] and d["n_pess"]
                         else "optimistic" if d["n_opt"] else "pessimistic")
    return sorted(agg.values(), key=lambda d: (-d["n_fail"], -d["worst_rel_pct"]))

def rank_by_table_point(rows, metric):
    agg = {}
    for r, mc, lib, ae, rel in _failing(rows, metric):
        i1, i2 = arc_indices(r.get("Arc", ""))
        d = agg.setdefault((i1, i2), {"index1": i1, "index2": i2, "n_fail": 0,
                                      "worst_rel_pct": 0.0, "worst_err_ps": 0.0})
        d["n_fail"] += 1
        d["worst_rel_pct"] = max(d["worst_rel_pct"], rel)
        d["worst_err_ps"] = max(d["worst_err_ps"], ae)
    return sorted(agg.values(), key=lambda d: (-d["n_fail"], -d["worst_rel_pct"]))

def worst_arcs(rows, metric, top=20):
    out = []
    for r, mc, lib, ae, rel in _failing(rows, metric):
        i1, i2 = arc_indices(r.get("Arc", ""))
        out.append({"arc": r.get("Arc", ""), "cell": _cell_of(r.get("Arc", "")),
                    "index1": i1, "index2": i2, "mc": mc, "lib": lib,
                    "abs_err_ps": ae, "rel_pct": rel,
                    "direction": "optimistic" if lib < mc else "pessimistic"})
    return sorted(out, key=lambda d: -d["rel_pct"])[:top]
```
- [ ] **Step 4: run, expect pass.**
- [ ] **Step 5: commit** — `git commit -am "feat: outlier rankings by cell / table-point / worst-arc"`

## Task B2: matplotlib figure builder `analysis/plots.py`

**Files:** Create `cert_data_process/analysis/plots.py`; Test `tests/test_plots.py`

- [ ] **Step 1: failing test**
```python
# tests/test_plots.py
import matplotlib
matplotlib.use("Agg")
from cert_data_process.analysis.plots import metric_unit, build_scatter_figure, save_figure

PTS = [(40.0, 38.0, True, "combinational_A_..._3_5"),
       (30.0, 30.1, False, "combinational_B_..._3_6")]

def test_metric_unit():
    assert metric_unit("Late_Sigma") == "ps"
    assert metric_unit("Skew") == ""

def test_build_and_save(tmp_path):
    for mode in ("lib_vs_mc", "residual"):
        fig = build_scatter_figure(PTS, "Late_Sigma", mode=mode, rel_threshold=0.03)
        assert fig is not None
        p = tmp_path / f"{mode}.png"
        save_figure(fig, p, dpi=150)
        assert p.exists() and p.stat().st_size > 1000
```
- [ ] **Step 2: run, expect fail** (ModuleNotFoundError).
- [ ] **Step 3: implement.**
```python
# cert_data_process/analysis/plots.py
"""Professional outlier scatter via matplotlib (no pyplot -> headless-safe + Tk-embeddable).
Build a Figure with build_scatter_figure(); the GUI wraps it in FigureCanvasTkAgg, tests
render it via the Agg backend and save_figure()."""
from __future__ import annotations
from matplotlib.figure import Figure

_PS = {"Nominal", "Early_Sigma", "Late_Sigma", "Std", "Meanshift"}

def metric_unit(metric: str) -> str:
    return "ps" if metric in _PS else ""

def _ulabel(metric: str) -> str:
    u = metric_unit(metric)
    return f"{metric} ({u})" if u else metric

def build_scatter_figure(points, metric, mode="lib_vs_mc", highlight=None, rel_threshold=None):
    """points: list of (mc, lib, is_outlier, arc). highlight: set of arcs to emphasize."""
    highlight = highlight or set()
    fig = Figure(figsize=(6, 5), dpi=120)
    ax = fig.add_subplot(111)
    mcs = [p[0] for p in points]; libs = [p[1] for p in points]
    if mode == "residual":
        xs = mcs
        ys = [((lib - mc) / abs(mc) * 100.0 if mc else 0.0) for mc, lib in zip(mcs, libs)]
        ax.axhline(0, color="#9ec5fe", lw=1)
        if rel_threshold:
            ax.axhline(rel_threshold * 100, color="#f3b", ls="--", lw=0.8)
            ax.axhline(-rel_threshold * 100, color="#f3b", ls="--", lw=0.8)
        ax.set_xlabel(f"MC {_ulabel(metric)}"); ax.set_ylabel("Rel error (%)")
    else:
        xs, ys = mcs, libs
        lo = min(mcs + libs); hi = max(mcs + libs)
        ax.plot([lo, hi], [lo, hi], color="#9ec5fe", ls="--", lw=1)  # y=x
        if rel_threshold:
            ax.fill_between([lo, hi], [lo * (1 - rel_threshold), hi * (1 - rel_threshold)],
                            [lo * (1 + rel_threshold), hi * (1 + rel_threshold)],
                            color="#9ec5fe", alpha=0.12)
        ax.set_xlabel(f"MC {_ulabel(metric)}"); ax.set_ylabel(f"Lib {_ulabel(metric)}")
    for (x, y, p) in zip(xs, ys, points):
        is_out, arc = p[2], p[3]
        big = arc in highlight
        ax.scatter([x], [y], s=(42 if big else 12),
                   c=("#dc2626" if is_out else "#94a3b8"),
                   edgecolors=("black" if big else "none"), zorder=3 if big else 2)
    ax.set_title(f"{metric}  (n={len(points)}, red = outlier)")
    ax.grid(True, color="#e5e7eb", lw=0.6)
    fig.tight_layout()
    return fig

def save_figure(fig, path, dpi=200) -> None:
    fig.savefig(str(path), dpi=dpi, bbox_inches="tight")
```
- [ ] **Step 4: run, expect pass.**
- [ ] **Step 5: commit** — `git commit -am "feat: matplotlib outlier figure builder (lib-vs-mc + residual, high-dpi)"`

## Task B3: enriched outlier drill-down panel

**Files:** Modify `cert_data_process/app/gui.py`; Test `tests/test_app_smoke.py`

- [ ] **Step 1: replace `_open_scatter` with the enriched panel.** Keep the existing Canvas drawing as a private fallback `_open_scatter_canvas` (rename the current body). New `_open_scatter`:
```python
    def _open_scatter(self, rid, corner, row_type, metric, label):
        tk = self.tk
        from tkinter import messagebox
        if not rid:
            return messagebox.showinfo("Scatter", "No batch directory for this point.")
        csvp = _perarc.find_per_arc_csv(runs.batch_dir(self.runs_root, rid), corner, row_type, metric)
        if not csvp:
            return messagebox.showinfo("Scatter", "Per-arc data not found for this point.")
        rows = _perarc.load_rows(csvp)
        pts = _perarc.scatter_points(rows, metric)
        if not pts:
            return messagebox.showinfo("Scatter", "No covered arcs to plot.")
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
            from ..analysis import plots as _plots
        except Exception:
            return self._open_scatter_canvas(rid, corner, row_type, metric, label, pts)
        self._open_scatter_mpl(label, metric, rows, pts, FigureCanvasTkAgg, NavigationToolbar2Tk, _plots)
```
- [ ] **Step 2: implement the mpl panel** (rankings + residual toggle + Save PNG + click-to-highlight):
```python
    def _open_scatter_mpl(self, label, metric, rows, pts, FigureCanvasTkAgg, NavToolbar, plots):
        tk, ttk = self.tk, self.ttk
        from ..analysis import outliers as _o
        win = tk.Toplevel(self.root); win.title(f"Outlier analysis — {label}")
        state = {"mode": "lib_vs_mc", "highlight": set()}
        left = ttk.Frame(win); left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(win, padding=6); right.pack(side="right", fill="y")
        bar = ttk.Frame(left); bar.pack(fill="x")
        mode_var = tk.StringVar(value="lib_vs_mc")
        holder = {"canvas": None, "toolbar": None}
        def redraw():
            if holder["canvas"]:
                holder["canvas"].get_tk_widget().destroy()
            if holder["toolbar"]:
                holder["toolbar"].destroy()
            fig = plots.build_scatter_figure(pts, metric, mode=state["mode"],
                                             highlight=state["highlight"], rel_threshold=0.03)
            c = FigureCanvasTkAgg(fig, master=left); c.draw()
            tb = NavToolbar(c, left); tb.update()
            c.get_tk_widget().pack(fill="both", expand=True)
            holder.update(canvas=c, toolbar=tb, fig=fig)
        def set_mode():
            state["mode"] = mode_var.get(); redraw()
        for key, txt in (("lib_vs_mc", "Lib vs MC"), ("residual", "Residual")):
            ttk.Radiobutton(bar, text=txt, value=key, variable=mode_var, command=set_mode).pack(side="left")
        def save_png():
            from tkinter import filedialog
            p = filedialog.asksaveasfilename(defaultextension=".png", initialfile="outliers.png")
            if p:
                plots.save_figure(holder["fig"], p, dpi=200)
        ttk.Button(bar, text="Save PNG", command=save_png).pack(side="right")
        def add_table(title, cols, data, arcs_for):
            ttk.Label(right, text=title, style="Sec.TLabel").pack(anchor="w", pady=(6, 0))
            tv = ttk.Treeview(right, columns=cols, show="headings", height=6, selectmode="browse")
            for c in cols:
                tv.heading(c, text=c); tv.column(c, width=84, anchor="center")
            for d in data:
                tv.insert("", "end", values=tuple(d.get(c.lower().replace(" ", "_"), d.get(c, "")) for c in cols))
            tv.pack(fill="x")
            def on_sel(_e, _tv=tv, _data=data, _arcs=arcs_for):
                sel = _tv.selection()
                if sel:
                    idx = _tv.index(sel[0])
                    state["highlight"] = _arcs(_data[idx]); redraw()
            tv.bind("<<TreeviewSelect>>", on_sel)
        cells = _o.rank_by_cell(rows, metric)
        tps = _o.rank_by_table_point(rows, metric)
        worst = _o.worst_arcs(rows, metric, top=20)
        arcset = lambda pred: {a for (_mc, _lib, _o2, a) in pts if pred(a)}
        add_table("Top cells", ["cell", "n_fail", "worst_rel_pct"], cells,
                  lambda d: arcset(lambda a: _o._cell_of(a) == d["cell"]))
        add_table("Top table points", ["index1", "index2", "n_fail"], tps,
                  lambda d: arcset(lambda a: _o.arc_indices(a) == (d["index1"], d["index2"])))
        add_table("Worst arcs", ["cell", "rel_pct", "direction"], worst,
                  lambda d: {d["arc"]})
        redraw()
```
And rename the old Canvas body to `_open_scatter_canvas(self, rid, corner, row_type, metric, label, pts)` (it already has `pts`; drop the reload).
- [ ] **Step 3: extend smoke test** — under mocked tk, matplotlib import inside `_open_scatter` will succeed (real matplotlib) but `FigureCanvasTkAgg(master=<MagicMock>)` may fail; guard by calling only the pure pieces in the smoke test:
```python
    # exercise ranking + figure build headlessly (panel embedding needs a real display)
    import matplotlib; matplotlib.use("Agg")
    from cert_data_process.analysis import plots as _plots, outliers as _o
    pts = [(40.0, 38.0, True, "combinational_A_Z_rise_A_rise_NO_CONDITION_3_5")]
    assert _plots.build_scatter_figure(pts, "Late_Sigma", mode="residual", rel_threshold=0.03) is not None
    assert _o.rank_by_cell([{"Arc": pts[0][3], "Late_Sigma_MC_value": "40",
                             "Late_Sigma_Lib_value": "38", "Late_Sigma_Final_Status": "Fail"}],
                            "Late_Sigma")[0]["cell"] == "A"
```
- [ ] **Step 4: run** — `PYTHONPATH=. python -m pytest tests/test_app_smoke.py tests/test_plots.py tests/test_outliers.py -q` → pass.
- [ ] **Step 5: commit** — `git commit -am "feat: enriched outlier panel (rankings + matplotlib plot + residual toggle + PNG export)"`

---

## Task FINAL: full regression + push

- [ ] **Step 1** — `PYTHONPATH=. python -m pytest tests/ -q` → all pass.
- [ ] **Step 2** — `python -m py_compile cert_data_process/audit.py cert_data_process/analysis/plots.py cert_data_process/cli.py cert_data_process/app/gui.py && PYTHONPATH=. python -c "import cert_data_process.audit, cert_data_process.analysis.plots; print('ok')"`
- [ ] **Step 3 (after user confirmation)** — `git push origin main`
- [ ] **Step 4** — print the exact files to copy to the host: `cert_data_process/audit.py` (new), `cert_data_process/analysis/plots.py` (new), `cert_data_process/analysis/outliers.py`, `cert_data_process/cli.py`, `cert_data_process/web/executor.py`, `cert_data_process/app/gui.py`, `cert_data_process/stages/get_pr_sigma.py` + `get_pr_moments.py` (if A4b changed them).

---

## Self-review

**Spec coverage:**
- §2 audit module (Finding/audit_stage/PATTERNS/summarize/format_block/write_report) → A1–A3. ✅
- §3 orchestration (on_finding, report, manifest summary, status-poll path) → A4, A4b, A5, A6. ✅
- §4 robustness (never crash; missing log → structured only; cap; de-dupe) → A1 de-dupe, A2 try/except, A3 cap. ✅
- §8.1 rankings → B1. ✅  §8.2 plots (units, modes, save) → B2. ✅  §8.3 panel (embed, toggle, rankings, fallback, Save PNG) → B3. ✅
- §8.4 tests → test_audit, test_outliers (extended), test_plots, smoke. ✅

**Placeholder scan:** none — every code step is complete and runnable.

**Type consistency:** `Finding(severity, stage, code, message, detail, pointer)` used identically in A1–A3 and rendered via dicts (`findings_to_dicts`) in A5/A6. `build_scatter_figure(points, metric, mode, highlight, rel_threshold)` and `points=(mc, lib, is_outlier, arc)` match `perarc.scatter_points` output and B3 usage. Ranking dict keys (`cell`, `n_fail`, `worst_rel_pct`, `index1/index2`, `arc`, `rel_pct`, `direction`) consistent between B1 and B3 tables.

**Note:** A4b is conditional — verify current PR-stage stdout capture before editing; if the `DATA_HEALTH` lines already land in a `log_file`, that task is a no-op beyond confirming.
