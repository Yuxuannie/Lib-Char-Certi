"""Generate the run's HTML dashboard (G5).

Reads the run artifacts (stage results + pr/sigma + pr/moments PR tables), builds
a CERTI_DATA object and injects it into the self-contained console template
(gui/certi_console.html) written to web_app/index.html. Air-gap safe (stdlib
only, no CDN/npm). Falls back to a minimal page if the template is unavailable.
"""

from __future__ import annotations

import csv
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from cert_data_process.config import CertDataProcessConfig

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = _REPO_ROOT / "gui" / "certi_console.html"
_PIPELINE_STAGES = {
    "fmc_combine_data", "lib_join_sigma", "build_pr_table",
    "get_pr_moments", "generate_pr_web_app",
}


@dataclass(frozen=True)
class PrWebAppResult:
    stage_execution: dict[str, Any]
    compatibility_stage_report: dict[str, Any]

    @property
    def failed(self) -> bool:
        return self.stage_execution["status"] == "failed"


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _read_csv(path: Path) -> Optional[tuple[list[str], list[list[str]]]]:
    if not path.is_file():
        return None
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    return (rows[0], rows[1:]) if rows else None


def _num(value: str) -> Optional[float]:
    """Parse a '93.2%' / '93.2' cell to float; '', 'N/A', non-numeric -> None."""
    if value is None:
        return None
    s = str(value).strip().rstrip("%").strip()
    if not s or s.upper() == "N/A":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _int(value: str) -> int:
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


def _sigma_rows(out: Path) -> list[dict[str, Any]]:
    result = []
    for d in _rows_as_dicts(out / "pr" / "sigma" / "sigma_PR_table_with_waivers.csv"):
        result.append({
            "corner": d.get("Corner", ""),
            "type": d.get("Type", ""),
            "eBase": _num(d.get("Early_Sigma_Base_PR")),
            "eW1": _num(d.get("Early_Sigma_PR_with_Waiver1")),
            "lBase": _num(d.get("Late_Sigma_Base_PR")),
            "lW1": _num(d.get("Late_Sigma_PR_with_Waiver1")),
            "total": _int(d.get("Total_Arcs")),
            "covered": _int(d.get("Covered")),
            "health": d.get("Data_Health", "NO_DATA"),
        })
    return result


def _moments_rows(out: Path) -> list[dict[str, Any]]:
    result = []
    for d in _rows_as_dicts(out / "pr" / "moments" / "moments_PR_table.csv"):
        result.append({
            "corner": d.get("Corner", ""),
            "type": d.get("Type", ""),
            "ms": _num(d.get("Meanshift_Base_PR")),
            "std": _num(d.get("Std_Base_PR")),
            "skew": _num(d.get("Skew_Base_PR")),
            "total": _int(d.get("Total_Arcs")),
            "covered": _int(d.get("Covered")),
            "health": d.get("Data_Health", "NO_DATA"),
        })
    return result


def _build_certi_data(config: CertDataProcessConfig, stage_execution: list[dict[str, Any]]) -> dict:
    out = config.output_dir
    batch_id = f"{config.process}_{config.process_version}_{config.vendor}".replace(".", "p")
    batch = {
        "id": batch_id,
        "name": f"{config.process} {config.process_version} · {config.vendor}",
        "vendor": config.vendor,
        "process": config.process,
        "version": config.process_version,
        "when": "",
        "libdir": str(config.lib_dir),
        "recipe": str(out.name),
        "stages": [
            {
                "stage": st.get("stage", ""),
                "status": st.get("status", ""),
                "pipeline": st.get("pipeline", ""),
                "reason": st.get("reason", ""),
            }
            for st in stage_execution
            if st.get("stage") in _PIPELINE_STAGES
        ],
        "sigma": _sigma_rows(out),
        "moments": _moments_rows(out),
    }
    return {"batches": [batch]}


def _inject(template_html: str, certi_data: dict) -> str:
    payload = json.dumps(certi_data, separators=(",", ":")).replace("</", "<\\/")
    inject = f"<script>window.CERTI_DATA = {payload};</script>"
    if "</head>" in template_html:
        return template_html.replace("</head>", inject + "\n</head>", 1)
    return inject + template_html


def _fallback_html(config: CertDataProcessConfig, certi_data: dict) -> str:
    # Minimal honest page if the console template is unavailable.
    batch = certi_data["batches"][0]
    rows = "".join(
        f"<tr><td>{_esc(r['corner'])}</td><td>{_esc(r['type'])}</td>"
        f"<td>{_esc(r['lBase'])}</td><td>{_esc(r['covered'])}/{_esc(r['total'])}</td>"
        f"<td>{_esc(r['health'])}</td></tr>"
        for r in batch["sigma"]
    )
    return (
        "<!doctype html><meta charset='utf-8'><title>cert_data_process run</title>"
        f"<h1>{_esc(batch['name'])}</h1>"
        "<p>Console template (gui/certi_console.html) not found; minimal view.</p>"
        "<table border=1 cellpadding=6><tr><th>Corner</th><th>Type</th>"
        "<th>Late Base PR</th><th>Coverage</th><th>Data_Health</th></tr>"
        f"{rows}</table>"
    )


def run_generate_pr_web_app(config: CertDataProcessConfig, stage_execution: list[dict[str, Any]]) -> PrWebAppResult:
    web_dir = config.output_dir / "web_app"
    web_dir.mkdir(parents=True, exist_ok=True)
    index = web_dir / "index.html"

    certi_data = _build_certi_data(config, stage_execution)
    used_template = False
    try:
        if _TEMPLATE.is_file():
            index.write_text(_inject(_TEMPLATE.read_text(encoding="utf-8"), certi_data), encoding="utf-8")
            used_template = True
        else:
            index.write_text(_fallback_html(config, certi_data), encoding="utf-8")
    except OSError:
        index.write_text(_fallback_html(config, certi_data), encoding="utf-8")

    return PrWebAppResult(
        stage_execution={
            "stage": "generate_pr_web_app",
            "pipeline": "sigma,moments",
            "status": "passed",
            "web_index": str(index),
            "used_console_template": used_template,
        },
        compatibility_stage_report={
            "stage": "generate_pr_web_app",
            "status": "not_evaluated",
            "reason": "UI parity against legacy flow is not required.",
        },
    )
