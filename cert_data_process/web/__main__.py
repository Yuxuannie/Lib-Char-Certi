"""Launch the Lib-Char-Certi console server: `python -m cert_data_process.web`."""

from __future__ import annotations

import argparse
import sys

from . import runs
from .server import serve


def _harden_stdout() -> None:
    """EDA hosts often use a latin-1 stdout; never crash on a stray Unicode char."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")  # py3.7+
        except (AttributeError, ValueError):
            pass


def main() -> None:
    _harden_stdout()
    ap = argparse.ArgumentParser(
        prog="cert_data_process.web",
        description="Lib-Char-Certi local console server (configure, launch, view, compare).",
    )
    ap.add_argument("--runs-dir", default=None, help="Runs root (default ./certi_runs or $CERTI_RUNS_DIR).")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--batch-concurrency", type=int, default=2, help="Concurrent batches (default 2).")
    ap.add_argument("--liberate-budget", type=int, default=4,
                    help="Global cap on concurrent liberate processes across all batches (default 4).")
    args = ap.parse_args()
    serve(runs.resolve_runs_root(args.runs_dir), port=args.port, host=args.host,
          batch_concurrency=args.batch_concurrency, liberate_budget=args.liberate_budget)


if __name__ == "__main__":
    main()
