"""Launch the Lib-Char-Certi desktop console: `python -m cert_data_process.app`.

Single-process Tkinter GUI — no HTTP, no port, no localhost/host-matching.
Displays over X11/Exceed like a terminal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..web import runs


def _harden_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")  # py3.7+; latin-1 EDA hosts
        except (AttributeError, ValueError):
            pass


def main() -> None:
    _harden_stdout()
    ap = argparse.ArgumentParser(
        prog="cert_data_process.app",
        description="Lib-Char-Certi desktop console (configure, launch, view, compare).",
    )
    ap.add_argument("--runs-dir", default=None, help="Runs root (default ./certi_runs or $CERTI_RUNS_DIR).")
    ap.add_argument("--demo", action="store_true",
                    help="Open the bundled synthetic demo run (no real data needed) — "
                         "ideal for a first look or following the tutorial.")
    ap.add_argument("--batch-concurrency", type=int, default=2, help="Concurrent batches (default 2).")
    ap.add_argument("--liberate-budget", type=int, default=4,
                    help="Global cap on concurrent liberate processes across batches (default 4).")
    args = ap.parse_args()

    runs_dir = args.runs_dir
    if args.demo:
        demo_dir = Path(__file__).resolve().parent.parent / "demo_run"
        if not demo_dir.is_dir():
            print(f"ERROR: bundled demo not found at {demo_dir}.")
            print("  Regenerate it with: python scripts/make_demo_run.py")
            raise SystemExit(2)
        runs_dir = str(demo_dir)
        print(f"Launching with bundled DEMO data (synthetic): {demo_dir}")

    try:
        import tkinter  # noqa: F401
    except Exception:
        print("ERROR: this Python has no Tkinter; cannot launch the desktop app.")
        print("  Run the test build instead, or use: python -m cert_data_process.web")
        raise SystemExit(2)

    from .gui import CertiApp
    CertiApp(runs.resolve_runs_root(runs_dir),
             batch_concurrency=args.batch_concurrency,
             liberate_budget=args.liberate_budget).run()


if __name__ == "__main__":
    main()
