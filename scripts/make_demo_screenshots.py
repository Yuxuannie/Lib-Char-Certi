#!/usr/bin/env python3
"""Capture tutorial screenshots of the desktop console against the bundled demo.

Drives a real CertiApp (no mainloop — manual update()) through each tab, then
screencaptures the window region. macOS uses `screencapture`; Linux uses `import`
(ImageMagick) or `gnome-screenshot`. Images land in docs/images/.

Run on a machine with a display:  python scripts/make_demo_screenshots.py
"""

from __future__ import annotations

import platform
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from cert_data_process.app.gui import CertiApp  # noqa: E402
from cert_data_process.web import runs  # noqa: E402

DEMO = REPO / "cert_data_process" / "demo_run"
OUT = REPO / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)


def _shoot(widget, path: Path) -> bool:
    widget.update_idletasks()
    widget.lift()
    try:
        widget.attributes("-topmost", True)
    except Exception:
        pass
    widget.update()
    time.sleep(0.4)
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    w, h = widget.winfo_width(), widget.winfo_height()
    sysname = platform.system()
    if sysname == "Darwin":
        cmd = ["screencapture", "-x", "-R", f"{x},{y},{w},{h}", str(path)]
    elif sysname == "Linux":
        cmd = ["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}", str(path)]
    else:
        print(f"  unsupported platform {sysname}")
        return False
    try:
        subprocess.run(cmd, check=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  capture failed: {exc}")
        return False
    ok = path.is_file() and path.stat().st_size > 2000
    print(f"  {'OK ' if ok else 'EMPTY'} {path.name} ({path.stat().st_size if path.is_file() else 0} B)")
    return ok


def main():
    rid = runs.read_index(DEMO)[0]["id"]
    corner = "ssgnp_0p675v_125c"
    app = CertiApp(DEMO)
    root = app.root
    root.geometry("1180x760")
    root.update()

    # 1) Setup tab
    app.nb.select(app.tab_setup)
    _shoot(root, OUT / "01_setup.png")

    # 2) Results (loaded, Waiver1 then base verdict differences are visible)
    app.load_results(rid)
    _shoot(root, OUT / "02_results.png")

    # 3) PR Status consolidated pivot
    app.nb.select(app.tab_pr)
    app._render_pr_status()
    _shoot(root, OUT / "03_pr_status.png")

    # 4) Outliers — base basis shows the most sub-95% points
    app.pr_basis = "base"
    app.nb.select(app.tab_out)
    app._render_outliers()
    _shoot(root, OUT / "04_outliers.png")

    # 5) Common offenders
    app.nb.select(app.tab_common)
    try:
        app._render_common()
    except Exception as exc:
        print(f"  common render: {exc}")
    _shoot(root, OUT / "05_common.png")

    # 6) Outlier scatter drill-down (the cross-check centerpiece)
    try:
        app._open_scatter(rid, corner, "hold", "Late_Sigma", "ocv_const_hold — DEMO 125c")
        # the scatter opens a Toplevel; grab the newest one
        tops = [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"]
        if tops:
            tops[-1].geometry("1100x680")
            _shoot(tops[-1], OUT / "06_scatter.png")
        else:
            print("  no scatter Toplevel found")
    except Exception as exc:
        print(f"  scatter: {exc}")

    root.destroy()


if __name__ == "__main__":
    main()
