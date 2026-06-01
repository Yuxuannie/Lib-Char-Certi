"""Shared builders for the CERTI_DATA batch shape + run records (stdlib only).

One source of truth for parsing the PR tables into the rows the dashboard renders
and the runs store persists, so the console and history always agree.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Optional

_PIPELINE_STAGES = {
    "fmc_combine_data", "lib_join_sigma", "build_pr_table",
    "get_pr_moments", "generate_pr_web_app",
}


def _read_csv(path: Path) -> Optional[tuple[list[str], list[list[str]]]]:
    if not path.is_file():
        return None
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    return (rows[0], rows[1:]) if rows else None


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().rstrip("%").strip()
    if not s or s.upper() == "N/A":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _int(value: Any) -> int:
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return 0


def _rows_as_dicts(path: Path) -> list[dict[str, str]]:
    data = _read_csv(path)
    if data is None:
        return []
    header, rows = data
    return [dict(zip(header, r)) for r in rows]


def _coverage(d: dict) -> dict:
    """Coverage fields, honest about absence: a table without the coverage
    columns is UNKNOWN (old format), NOT a fabricated NO_DATA over 0 arcs."""
    if "Total_Arcs" not in d and "Data_Health" not in d:
        return {"total": None, "covered": None, "health": "UNKNOWN"}
    return {"total": _int(d.get("Total_Arcs")), "covered": _int(d.get("Covered")),
            "health": d.get("Data_Health") or "UNKNOWN"}


def build_sigma_rows(out: Path) -> list[dict[str, Any]]:
    rows = []
    for d in _rows_as_dicts(out / "pr" / "sigma" / "sigma_PR_table_with_waivers.csv"):
        row = {
            "corner": d.get("Corner", ""),
            "type": d.get("Type", ""),
            "nomBase": _num(d.get("Nominal_Base_PR")),
            "nomW1": _num(d.get("Nominal_PR_with_Waiver1")),
            "eBase": _num(d.get("Early_Sigma_Base_PR")),
            "eW1": _num(d.get("Early_Sigma_PR_with_Waiver1")),
            "lBase": _num(d.get("Late_Sigma_Base_PR")),
            "lW1": _num(d.get("Late_Sigma_PR_with_Waiver1")),
        }
        row.update(_coverage(d))
        rows.append(row)
    return rows


def build_moments_rows(out: Path) -> list[dict[str, Any]]:
    rows = []
    for d in _rows_as_dicts(out / "pr" / "moments" / "moments_PR_table.csv"):
        row = {
            "corner": d.get("Corner", ""),
            "type": d.get("Type", ""),
            "ms": _num(d.get("Meanshift_Base_PR")),
            "std": _num(d.get("Std_Base_PR")),
            "skew": _num(d.get("Skew_Base_PR")),
            "msW1": _num(d.get("Meanshift_PR_with_Waiver1")),
            "stdW1": _num(d.get("Std_PR_with_Waiver1")),
            "skewW1": _num(d.get("Skew_PR_with_Waiver1")),
        }
        row.update(_coverage(d))
        rows.append(row)
    return rows


# ---- per-type results view + certification verdict (B) ----
PASS_THRESHOLD = 95.0
TYPE_ORDER = ["delay", "slew", "hold", "mpw"]
TYPE_METRICS = {
    "delay": ["Early_Sigma", "Late_Sigma", "Meanshift", "Std", "Skew"],
    "slew": ["Early_Sigma", "Late_Sigma", "Meanshift", "Std", "Skew"],
    "hold": ["Late_Sigma"],
    "mpw": ["Late_Sigma"],
}
# metric -> (source, base_key, w1_key) where source is 'sigma' or 'moments'
_METRIC_SRC = {
    "Early_Sigma": ("sigma", "eBase", "eW1"),
    "Late_Sigma": ("sigma", "lBase", "lW1"),
    "Meanshift": ("moments", "ms", "msW1"),
    "Std": ("moments", "std", "stdW1"),
    "Skew": ("moments", "skew", "skewW1"),
}


def _metric_value(metric: str, basis: str, sig: Optional[dict], mom: Optional[dict]) -> Optional[float]:
    src, base_key, w1_key = _METRIC_SRC[metric]
    row = sig if src == "sigma" else mom
    if not row:
        return None
    return row.get(w1_key if basis == "w1" else base_key)


def per_type_sections(record: dict, basis: str = "base") -> list[dict]:
    """Group results by type (delay/slew/hold/mpw). Returns ordered sections:
    {type, metrics:[names], rows:[{corner, health, values:{metric:pr}}]}."""
    sigma = {(r["corner"], r["type"]): r for r in record.get("sigma", [])}
    moments = {(r["corner"], r["type"]): r for r in record.get("moments", [])}
    corners_by_type: dict[str, list] = {}
    for (corner, typ) in list(sigma) + list(moments):
        corners_by_type.setdefault(typ, [])
        if corner not in corners_by_type[typ]:
            corners_by_type[typ].append(corner)
    sections = []
    for typ in TYPE_ORDER:
        if typ not in corners_by_type:
            continue
        metrics = TYPE_METRICS[typ]
        rows = []
        for corner in corners_by_type[typ]:
            sig = sigma.get((corner, typ))
            mom = moments.get((corner, typ))
            health = (sig or mom or {}).get("health", "UNKNOWN")
            rows.append({
                "corner": corner, "health": health,
                "values": {m: _metric_value(m, basis, sig, mom) for m in metrics},
            })
        sections.append({"type": typ, "metrics": metrics, "rows": rows})
    return sections


def certification_verdict(record: dict, basis: str = "base", threshold: float = PASS_THRESHOLD) -> dict:
    """PASS iff every shown type-metric pass rate (all corners) >= threshold.
    Returns {passed, threshold, basis, failing:[(type,corner,metric,pr)], n_evaluated}."""
    failing = []
    n = 0
    for section in per_type_sections(record, basis):
        for row in section["rows"]:
            for metric, pr in row["values"].items():
                if pr is None:
                    continue
                n += 1
                if pr < threshold:
                    failing.append((section["type"], row["corner"], metric, pr))
    return {"passed": (n > 0 and not failing), "threshold": threshold, "basis": basis,
            "failing": failing, "n_evaluated": n}


def flat_export_rows(record: dict, basis: str = "base") -> list[list]:
    """Flat, copiable table for CSV export: header + [type,corner,metric,pass_rate,health]."""
    out = [["Type", "Corner", "Metric", "Pass_Rate", "Coverage_Health"]]
    for section in per_type_sections(record, basis):
        for row in section["rows"]:
            for metric, pr in row["values"].items():
                out.append([section["type"], row["corner"], metric,
                            "" if pr is None else f"{pr:.1f}", row["health"]])
    return out


def overall_status(stage_execution: list[dict[str, Any]]) -> str:
    statuses = {st.get("status") for st in stage_execution if st.get("stage") in _PIPELINE_STAGES}
    if "failed" in statuses:
        return "failed"
    if "partial" in statuses:
        return "partial"
    if statuses and statuses <= {"passed", "skipped"}:
        return "passed"
    return "skipped"


def worst_health(rows: list[dict[str, Any]]) -> str:
    healths = {r.get("health") for r in rows}
    if "NO_DATA" in healths:
        return "NO_DATA"
    if "LOW_COVERAGE" in healths:
        return "LOW_COVERAGE"
    return "OK" if healths else "NO_DATA"


def mean_late_sigma(sigma_rows: list[dict[str, Any]]) -> Optional[float]:
    vals = [r["lBase"] for r in sigma_rows if r.get("health") != "NO_DATA" and r.get("lBase") is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def build_batch(config, stage_execution: list[dict[str, Any]], *, batch_id: str, name: str, when_utc: str) -> dict:
    """Build the CERTI_DATA batch object for one run (also the run_record body)."""
    out = config.output_dir
    sigma = build_sigma_rows(out)
    moments = build_moments_rows(out)
    return {
        "schema_version": 1,
        "id": batch_id,
        "name": name,
        "when_utc": when_utc,
        "vendor": config.vendor,
        "process": config.process,
        "version": config.process_version,
        "vt_type": getattr(config, "vt_type", ""),
        "rc_type": getattr(config, "rc_type", ""),
        "library_type": getattr(config, "library_type", "auto"),
        "recipe": str(Path(out).name),
        "libdir": str(config.lib_dir),
        "config": {
            "vendor": config.vendor,
            "process": config.process,
            "process_version": config.process_version,
            "corners": list(config.corners),
            "types": list(config.types),
            "vt_type": getattr(config, "vt_type", ""),
            "rc_type": getattr(config, "rc_type", ""),
            "library_type": getattr(config, "library_type", "auto"),
            "fmc_mode": getattr(config, "fmc_mode", "decks"),
            "fmc_golden_dir": str(config.fmc_golden_dir) if config.fmc_golden_dir else None,
            "fmc_input_dir": str(config.fmc_input_dir) if config.fmc_input_dir else None,
            "lib_dir": str(config.lib_dir),
            "output_dir": str(out),
        },
        "status": overall_status(stage_execution),
        "stages": [
            {"stage": st.get("stage", ""), "status": st.get("status", ""),
             "pipeline": st.get("pipeline", ""), "reason": st.get("reason", "")}
            for st in stage_execution if st.get("stage") in _PIPELINE_STAGES
        ],
        "sigma": sigma,
        "moments": moments,
    }


def build_index_summary(batch: dict) -> dict:
    """Lightweight row for index.json / the History list."""
    return {
        "id": batch["id"],
        "name": batch["name"],
        "when_utc": batch["when_utc"],
        "vendor": batch.get("vendor", ""),
        "process": batch.get("process", ""),
        "version": batch.get("version", ""),
        "status": batch.get("status", ""),
        "corners": batch.get("config", {}).get("corners", []),
        "mean_late_sigma": mean_late_sigma(batch.get("sigma", [])),
        "worst_health": worst_health(batch.get("sigma", [])),
    }
