"""Background batch executor for the control server (stdlib only).

Submits certification batches to a bounded thread pool (N concurrent batches).
A global liberate budget caps total liberate processes across all batches: the
per-batch lib_join pool size is set so batch_concurrency x workers <= budget, so
the RAM-tight host can't be swamped. Live per-stage status is tracked for polling.
"""

from __future__ import annotations

import os
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cert_data_process.config import build_config
from cert_data_process.cli import execute_stages  # main-thread import (no cycle); fail loud at startup
from . import runs, summary

_STAGE_ORDER = ["fmc_combine_data", "lib_join_sigma", "build_pr_table", "get_pr_moments", "generate_pr_web_app"]


class JobManager:
    def __init__(self, runs_root: Any, batch_concurrency: int = 2, liberate_budget: int = 4):
        self.runs_root = Path(runs_root)
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.batch_concurrency = max(1, int(batch_concurrency))
        self.liberate_budget = max(1, int(liberate_budget))
        # Coarse global cap: each batch's lib_join uses this many liberate workers,
        # so total ~= batch_concurrency * per_batch <= liberate_budget.
        per_batch = max(1, self.liberate_budget // self.batch_concurrency)
        os.environ["CERTI_LIB_JOIN_WORKERS"] = str(per_batch)
        self._pool = ThreadPoolExecutor(max_workers=self.batch_concurrency)
        self._lock = threading.Lock()
        self._status: dict[str, dict] = {}

    # ---- public API ----
    def submit(self, cfg: dict) -> str:
        """Validate + enqueue a batch. Raises ValueError on bad config."""
        name = (cfg.get("name") or f"{cfg.get('process','run')}_{cfg.get('process_version','')}_{cfg.get('vendor','')}").strip()
        when = datetime.now(timezone.utc)
        batch_id = runs.make_batch_id(name, when.strftime("%Y%m%d_%H%M%S"))
        out_dir = runs.batch_dir(self.runs_root, batch_id)

        config = build_config(  # raises ValueError -> caller returns 400
            vendor=cfg.get("vendor", ""),
            process=cfg.get("process", ""),
            process_version=cfg.get("process_version", ""),
            corners=cfg.get("corners", []),
            types=cfg.get("types", []),
            fmc_golden_dir=cfg.get("fmc_golden_dir") or None,
            full_mc_golden_dir=None,
            lib_dir=cfg.get("lib_dir", ""),
            output_dir=str(out_dir),
            fmc_mode=cfg.get("fmc_mode", "decks"),
            fmc_input_dir=cfg.get("fmc_input_dir") or None,
            vt_type=cfg.get("vt_type", ""),
            rc_type=cfg.get("rc_type", ""),
            library_type=cfg.get("library_type", "auto"),
            abs_tol_ps_by_corner=cfg.get("abs_tol_ps_by_corner") or {},
            lib_unit=cfg.get("lib_unit", ""),
            fmc_unit=cfg.get("fmc_unit", ""),
        )

        with self._lock:
            self._status[batch_id] = {
                "id": batch_id, "name": name, "state": "queued",
                "when_utc": when.isoformat(),
                "stages": {s: "pending" for s in _STAGE_ORDER},
                "findings": [],
                "started_utc": None, "ended_utc": None, "error": None,
            }
        fut = self._pool.submit(self._run, batch_id, config, name, when.isoformat())
        fut.add_done_callback(lambda f: self._on_future_done(batch_id, name, when.isoformat(), f))
        return batch_id

    def _on_future_done(self, batch_id: str, name: str, when_utc: str, fut) -> None:
        """Surface any exception the worker swallowed (e.g. an import error) so the
        job never silently sits at 'queued'."""
        try:
            exc = fut.exception()
        except Exception:
            exc = None
        if exc is None:
            return
        err = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        cur = self.status(batch_id)
        if cur and cur.get("state") in ("passed", "partial", "failed"):
            return  # _run already recorded a terminal state
        traceback.print_exception(type(exc), exc, exc.__traceback__)
        try:
            d = runs.batch_dir(self.runs_root, batch_id)
            d.mkdir(parents=True, exist_ok=True)
            (d / "error.log").write_text(err, encoding="utf-8")
            record = {"schema_version": 1, "id": batch_id, "name": name, "when_utc": when_utc,
                      "status": "failed", "stages": [], "sigma": [], "moments": [], "error": f"{type(exc).__name__}: {exc}"}
            runs.write_run_record(self.runs_root, batch_id, record)
            runs.update_index(self.runs_root, summary.build_index_summary(record))
        except OSError:
            pass
        self._set(batch_id, state="failed", error=f"{type(exc).__name__}: {exc}",
                  ended_utc=datetime.now(timezone.utc).isoformat())

    def status(self, batch_id: str) -> Optional[dict]:
        with self._lock:
            st = self._status.get(batch_id)
            return dict(st, stages=dict(st["stages"]), findings=list(st.get("findings", []))) if st else None

    def all_status(self) -> list[dict]:
        with self._lock:
            return [dict(st, stages=dict(st["stages"]), findings=list(st.get("findings", [])))
                    for st in self._status.values()]

    def _add_findings(self, batch_id: str, items: list) -> None:
        with self._lock:
            self._status[batch_id].setdefault("findings", []).extend(items)

    # ---- internal ----
    def _set(self, batch_id: str, **kw) -> None:
        with self._lock:
            self._status[batch_id].update(kw)

    def _set_stage(self, batch_id: str, stage: str, status: str) -> None:
        with self._lock:
            if stage in self._status[batch_id]["stages"]:
                self._status[batch_id]["stages"][stage] = status

    def _run(self, batch_id: str, config, name: str, when_utc: str) -> None:
        self._set(batch_id, state="running", started_utc=datetime.now(timezone.utc).isoformat())

        def on_stage(stage_dict: dict) -> None:
            self._set_stage(batch_id, stage_dict.get("stage", ""), stage_dict.get("status", ""))

        def on_finding(stage: str, items: list) -> None:
            self._add_findings(batch_id, items)

        try:
            stage_execution, _compat, _failed = execute_stages(config, on_stage=on_stage, on_finding=on_finding)
            batch = summary.build_batch(config, stage_execution, batch_id=batch_id, name=name, when_utc=when_utc)
            runs.write_run_record(self.runs_root, batch_id, batch)
            runs.update_index(self.runs_root, summary.build_index_summary(batch))
            self._set(batch_id, state=batch["status"], ended_utc=datetime.now(timezone.utc).isoformat())
        except Exception as exc:  # never let a job crash the server
            err = f"{exc.__class__.__name__}: {exc}"
            traceback.print_exc()
            record = {
                "schema_version": 1, "id": batch_id, "name": name, "when_utc": when_utc,
                "status": "failed", "stages": [], "sigma": [], "moments": [], "error": err,
            }
            try:
                runs.write_run_record(self.runs_root, batch_id, record)
                runs.update_index(self.runs_root, summary.build_index_summary(record))
            except OSError:
                pass
            self._set(batch_id, state="failed", error=err, ended_utc=datetime.now(timezone.utc).isoformat())

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False)
