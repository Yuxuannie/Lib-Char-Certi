"""Voltage Margin integration (Phase A) — file-contract bridge to 3-Voltage_Margin_Tool.

The VM tool consumes the same ``*_fmc_cdns_lib_comp.rpt`` files our lib-join writes
to ``<batch>/combined/sigma``, fits lib-value-vs-voltage sensitivity per corner
family (15 mV max-adjacent-gap hard gate, enforced inside the VM tool), and emits
per-object voltage margins. We shell out to its ``run_analysis.py`` and read the
CSV outputs back — no cross-import, per the repo's interface-contract rule.

Phase A covers batches whose certified corners already span the voltage range
(e.g. batch_1's 4 corners at 15 mV spacing). Support-corner lib-only extraction
(no golden) is Phase B and not implemented here.
"""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path
from typing import Any, Optional


def vm_tool_dir() -> Path:
    """Location of the bundled Voltage Margin tool (repo_root/3-Voltage_Margin_Tool)."""
    return Path(__file__).resolve().parents[2] / "3-Voltage_Margin_Tool"


def build_cmd(data_dir, out_dir, corners, types, tool_dir=None) -> list:
    """Construct the run_analysis.py command (separated for testability)."""
    tool = Path(tool_dir) if tool_dir else vm_tool_dir()
    cmd = [
        "python3", str(tool / "run_analysis.py"), str(data_dir),
        "--output-dir", str(out_dir),
    ]
    vm_types = [t for t in types if t in ("delay", "slew", "hold")]
    if corners:
        cmd += ["--corners", *list(corners)]
    if vm_types:
        cmd += ["--types", *vm_types]
    return cmd


def read_csv_rows(path) -> tuple:
    """Return (header, rows) from a CSV, or ([], []) if missing/unreadable."""
    p = Path(path)
    if not p.is_file():
        return [], []
    try:
        with p.open(newline="", encoding="utf-8", errors="replace") as fh:
            r = list(csv.reader(fh))
    except OSError:
        return [], []
    return (r[0], r[1:]) if r else ([], [])


def read_outputs(out_dir) -> dict:
    """Read the VM output package CSVs we surface in the Analysis page."""
    out = Path(out_dir)
    summ_h, summ_r = read_csv_rows(out / "all_errors" / "margin_summary.csv")
    per_h, per_r = read_csv_rows(out / "all_errors" / "per_object_margin.csv")
    warn_h, warn_r = read_csv_rows(out / "sensitivity" / "sensitivity_warnings.csv")
    opt_h, opt_r = read_csv_rows(out / "optimistic_only" / "per_object_margin.csv")
    return {
        "summary": {"header": summ_h, "rows": summ_r},
        "per_object": {"header": per_h, "rows": per_r},
        "optimistic_per_object": {"header": opt_h, "rows": opt_r},
        "sensitivity_warnings": {"header": warn_h, "rows": warn_r},
    }


def run_voltage_margin(batch_dir, corners, types, tool_dir=None, timeout=1800) -> dict:
    """Run the VM tool on one batch's sigma rpts; return status + parsed outputs.

    Returns dict: ok, returncode, reason, out_dir, cmd, stdout_tail, stderr_tail, plus
    the parsed CSVs from read_outputs() when the run produced them.
    """
    # Resolve to ABSOLUTE paths: the VM subprocess runs with cwd=tool_dir, so a
    # relative batch path (e.g. certi_runs/<batch>) would resolve against the wrong
    # directory and "No such file or directory".
    bdir = Path(batch_dir).resolve()
    data_dir = bdir / "combined" / "sigma"
    out_dir = bdir / "voltage_margin"
    tool = Path(tool_dir) if tool_dir else vm_tool_dir()
    result: dict[str, Any] = {"ok": False, "out_dir": str(out_dir)}

    if not (tool / "run_analysis.py").is_file():
        result["reason"] = f"vm_tool_not_found: {tool / 'run_analysis.py'}"
        return result
    if not data_dir.is_dir() or not any(data_dir.glob("*_fmc_cdns_lib_comp.rpt")):
        result["reason"] = f"no_sigma_rpt_inputs: {data_dir}"
        return result

    cmd = build_cmd(data_dir, out_dir, corners, types, tool_dir=tool)
    result["cmd"] = " ".join(cmd)
    try:
        proc = subprocess.run(cmd, cwd=str(tool), capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["reason"] = f"run_failed: {exc}"
        return result

    result["returncode"] = proc.returncode
    result["stdout_tail"] = "\n".join((proc.stdout or "").splitlines()[-25:])
    result["stderr_tail"] = "\n".join((proc.stderr or "").splitlines()[-25:])
    result.update(read_outputs(out_dir))
    result["ok"] = proc.returncode == 0
    if not result["ok"]:
        result["reason"] = f"exit_{proc.returncode}"
    return result
