"""Generate a lightweight HTML dashboard for a run (G5 foundation).

Renders the run's stage statuses plus the sigma and moments PR tables with
color-coded Data_Health, so the data situation (G2) is visible at a glance and
a high PR over zero real cells cannot be read as success. Dependency-free
(stdlib csv only); robust to missing artifacts.
"""

from __future__ import annotations

import csv
import html
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from cert_data_process.config import CertDataProcessConfig

_STATUS_COLOR = {
    "passed": "#d4edda", "ok": "#d4edda",
    "partial": "#fff3cd", "skipped": "#e2e3e5",
    "failed": "#f8d7da",
}
_HEALTH_COLOR = {
    "OK": "#d4edda", "LOW_COVERAGE": "#fff3cd", "NO_DATA": "#f8d7da",
}


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _read_csv(path: Path) -> Optional[tuple[list[str], list[list[str]]]]:
    if not path.is_file():
        return None
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return None
    return rows[0], rows[1:]


def _pr_table_html(title: str, path: Path) -> str:
    data = _read_csv(path)
    if data is None:
        return f"<h2>{_esc(title)}</h2><p class='missing'>Not produced ({_esc(path.name)} missing — check coverage / lib).</p>"
    header, rows = data
    health_idx = header.index("Data_Health") if "Data_Health" in header else None
    thead = "".join(f"<th>{_esc(c)}</th>" for c in header)
    body = []
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            style = ""
            if health_idx is not None and i == health_idx:
                style = f" style='background:{_HEALTH_COLOR.get(cell, '#fff')};font-weight:bold'"
            cells.append(f"<td{style}>{_esc(cell)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        f"<h2>{_esc(title)}</h2>"
        f"<table><tr>{thead}</tr>{''.join(body)}</table>"
    )


def run_generate_pr_web_app(config: CertDataProcessConfig, stage_execution: list[dict[str, Any]]) -> PrWebAppResult:
    web_dir = config.output_dir / "web_app"
    web_dir.mkdir(parents=True, exist_ok=True)
    index = web_dir / "index.html"

    stage_rows = []
    for st in stage_execution:
        status = str(st.get("status", ""))
        color = _STATUS_COLOR.get(status.lower(), "#fff")
        stage_rows.append(
            f"<tr><td>{_esc(st.get('stage',''))}</td>"
            f"<td style='background:{color}'>{_esc(status)}</td>"
            f"<td>{_esc(st.get('pipeline',''))}</td>"
            f"<td>{_esc(st.get('reason',''))}</td></tr>"
        )

    out = config.output_dir
    sigma_html = _pr_table_html("Sigma PR (Base_PR + PR_with_Waiver1)", out / "pr" / "sigma" / "sigma_PR_table_with_waivers.csv")
    moments_html = _pr_table_html("Moments PR (Base_PR + PR_with_Waiver1)", out / "pr" / "moments" / "moments_PR_table.csv")

    style = (
        "<style>"
        "body{font-family:Arial,Helvetica,sans-serif;margin:24px;color:#222}"
        "table{border-collapse:collapse;margin-bottom:24px}"
        "th,td{border:1px solid #bbb;padding:6px 10px;text-align:center;font-size:13px}"
        "th{background:#f1f3f5}"
        ".missing{color:#a00;font-style:italic}"
        ".legend span{display:inline-block;padding:2px 8px;margin-right:8px;border:1px solid #bbb}"
        "</style>"
    )
    legend = (
        "<p class='legend'>Data_Health: "
        f"<span style='background:{_HEALTH_COLOR['OK']}'>OK</span>"
        f"<span style='background:{_HEALTH_COLOR['LOW_COVERAGE']}'>LOW_COVERAGE (&lt;90% covered)</span>"
        f"<span style='background:{_HEALTH_COLOR['NO_DATA']}'>NO_DATA (0 covered — PR not meaningful)</span>"
        "</p>"
    )
    html_doc = (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>cert_data_process run</title>{style}</head><body>"
        f"<h1>cert_data_process run dashboard</h1>"
        f"<p>output_dir: {_esc(out)}</p>"
        f"<h2>Stages</h2>"
        f"<table><tr><th>stage</th><th>status</th><th>pipeline</th><th>reason</th></tr>"
        f"{''.join(stage_rows)}</table>"
        f"{legend}"
        f"{sigma_html}"
        f"{moments_html}"
        f"</body></html>"
    )
    index.write_text(html_doc, encoding="utf-8")
    return PrWebAppResult(
        stage_execution={
            "stage": "generate_pr_web_app",
            "pipeline": "sigma,moments",
            "status": "passed",
            "web_index": str(index),
        },
        compatibility_stage_report={
            "stage": "generate_pr_web_app",
            "status": "not_evaluated",
            "reason": "UI parity against legacy flow is not required.",
        },
    )


@dataclass(frozen=True)
class PrWebAppResult:
    stage_execution: dict[str, Any]
    compatibility_stage_report: dict[str, Any]

    @property
    def failed(self) -> bool:
        return self.stage_execution["status"] == "failed"
