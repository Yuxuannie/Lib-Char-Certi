"""Helpers for parsing Full MC moment tables and netlist params."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


def parse_mc_sim_params(mc_sim_path: Path) -> dict[str, float | None]:
    cl = None
    rel_pin_slew = None
    for line in mc_sim_path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s.startswith(".param cl"):
            m = re.search(r"=\s*([-+0-9.eE]+)", s)
            if m:
                cl = float(m.group(1))
        elif s.startswith(".param rel_pin_slew"):
            m = re.search(r"=\s*([-+0-9.eE]+)", s)
            if m:
                rel_pin_slew = float(m.group(1))
    return {"cl": cl, "rel_pin_slew": rel_pin_slew}


def _extract_sample_moments_block(report_path: Path) -> Optional[list[str]]:
    content = report_path.read_text(encoding="utf-8", errors="replace")
    start = content.find("##Sample_Moments")
    if start == -1:
        return None
    end = content.find("##Response_Correlation_Matrix", start)
    if end == -1:
        return None
    return content[start:end].splitlines()


def parse_sample_moments(report_path: Path) -> dict[str, dict[str, float]]:
    """Return mapping like {'Nominal': {'meas_delay':.., 'meas_tt_out':..}, ...}."""

    lines = _extract_sample_moments_block(report_path)
    if not lines:
        return {}

    header_idx = None
    header_cols: list[str] = []
    for i, line in enumerate(lines):
        cols = re.split(r"\s+", line.strip())
        if {"half_tt_out", "meas_delay", "meas_tt_out"}.issubset(set(cols)):
            header_idx = i
            header_cols = cols
            break
    if header_idx is None:
        return {}

    idx_delay = header_cols.index("meas_delay")
    idx_slew = header_cols.index("meas_tt_out")

    data: dict[str, dict[str, float]] = {}
    for line in lines[header_idx + 1 :]:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        cols = re.split(r"\s+", s)
        if len(cols) <= max(idx_delay, idx_slew):
            continue
        metric = cols[0]
        try:
            delay_v = float(cols[idx_delay])
            slew_v = float(cols[idx_slew])
        except ValueError:
            continue
        data[metric] = {"meas_delay": delay_v, "meas_tt_out": slew_v}
    return data


def parse_sample_moments_legacy_rows(report_path: Path) -> list[list[str]]:
    """Return legacy-like rows for Layer A validation.

    Shape mirrors legacy `1-Parse/parse_mc_data.py` CSV output: first column is
    metric label, followed by `half_tt_out`, `meas_delay`, `meas_tt_out`.
    """

    lines = _extract_sample_moments_block(report_path)
    if not lines:
        return []

    header_idx = None
    header_cols: list[str] = []
    for i, line in enumerate(lines):
        cols = [c for c in re.split(r"\s+", line.strip()) if c]
        if {"half_tt_out", "meas_delay", "meas_tt_out"}.issubset(set(cols)):
            header_idx = i
            header_cols = cols
            break
    if header_idx is None:
        return []

    idx_half = header_cols.index("half_tt_out")
    idx_delay = header_cols.index("meas_delay")
    idx_slew = header_cols.index("meas_tt_out")

    rows: list[list[str]] = [["", "half_tt_out", "meas_delay", "meas_tt_out"]]
    for line in lines[header_idx + 1 :]:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        cols = [c for c in re.split(r"\s+", s) if c]
        if len(cols) <= max(idx_half, idx_delay, idx_slew):
            continue
        rows.append([cols[0], cols[idx_half], cols[idx_delay], cols[idx_slew]])
    return rows
