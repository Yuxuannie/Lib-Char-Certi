"""Pipeline audit: extract high-signal Findings from each stage (structured stage
dict + a pattern scan of the stage's captured log) and render them to the log
window / report / banner. Pure: no Tk, no subprocess."""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict


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
    seen = set()
    uniq = []
    for f in findings:
        k = (f.code, f.message)
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq
