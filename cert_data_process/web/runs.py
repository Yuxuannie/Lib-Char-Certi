"""File-based runs store + history index (stdlib only).

Each batch lives at runs_root/<id>/ (full output tree + run_record.json).
runs_root/index.json aggregates batch summaries for History/Compare. Writes are
atomic (temp + os.replace); the index upsert is guarded by a lock so the web
executor's concurrent batches don't corrupt it.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

DEFAULT_RUNS_DIR = "certi_runs"
_index_lock = threading.Lock()


def resolve_runs_root(runs_dir: Optional[Any] = None) -> Path:
    if runs_dir:
        return Path(runs_dir)
    env = os.environ.get("CERTI_RUNS_DIR")
    return Path(env) if env else Path(DEFAULT_RUNS_DIR)


def slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name).strip()).strip("_")
    return s or "batch"


def make_batch_id(name: str, timestamp: str) -> str:
    """timestamp like '20260531_125200' -> '<slug>_<timestamp>'."""
    return f"{slug(name)}_{timestamp}"


def batch_dir(runs_root: Any, batch_id: str) -> Path:
    return Path(runs_root) / batch_id


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_run_record(runs_root: Any, batch_id: str, record: dict) -> Path:
    path = batch_dir(runs_root, batch_id) / "run_record.json"
    _atomic_write_json(path, record)
    return path


def read_run_record(runs_root: Any, batch_id: str) -> Optional[dict]:
    path = batch_dir(runs_root, batch_id) / "run_record.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def read_index(runs_root: Any) -> list[dict]:
    path = Path(runs_root) / "index.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return sorted(data, key=lambda r: r.get("when_utc", ""), reverse=True)


def update_index(runs_root: Any, summary: dict) -> None:
    """Upsert one batch summary into index.json (last write wins per id)."""
    with _index_lock:
        items = [r for r in read_index(runs_root) if r.get("id") != summary.get("id")]
        items.append(summary)
        _atomic_write_json(Path(runs_root) / "index.json", items)
