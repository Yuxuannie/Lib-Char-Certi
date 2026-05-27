"""Generate a lightweight web app for run observability and PR-table discovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cert_data_process.config import CertDataProcessConfig


@dataclass(frozen=True)
class PrWebAppResult:
    stage_execution: dict[str, Any]
    compatibility_stage_report: dict[str, Any]

    @property
    def failed(self) -> bool:
        return self.stage_execution["status"] == "failed"


def run_generate_pr_web_app(config: CertDataProcessConfig, stage_execution: list[dict[str, Any]]) -> PrWebAppResult:
    web_dir = config.output_dir / "web_app"
    web_dir.mkdir(parents=True, exist_ok=True)
    index = web_dir / "index.html"
    rows = []
    for st in stage_execution:
        rows.append(
            f"<tr><td>{st.get('stage','')}</td><td>{st.get('status','')}</td><td>{st.get('pipeline','')}</td><td>{st.get('reason','')}</td></tr>"
        )
    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>cert_data_process run</title></head>
<body><h1>cert_data_process run dashboard</h1>
<p>output_dir: {config.output_dir}</p>
<table border='1' cellspacing='0' cellpadding='6'><tr><th>stage</th><th>status</th><th>pipeline</th><th>reason</th></tr>{''.join(rows)}</table>
<p>PR table candidates under: combined/sigma/</p>
</body></html>"""
    index.write_text(html, encoding='utf-8')
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
