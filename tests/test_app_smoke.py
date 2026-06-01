"""Construction smoke test for the Tk GUI using a mocked tkinter.

The dev box has no display, so the GUI can't really render. But mocking tkinter
lets us actually instantiate CertiApp and run its build/render methods — which
catches construction-time NameErrors / undefined-name bugs (e.g. a method using
`tk.` without binding `tk = self.tk`). Mocks accept any attribute, so only real
Python name-resolution errors surface — exactly the class we keep hitting.
"""

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_tk(monkeypatch):
    fake = MagicMock(name="tkinter")
    monkeypatch.setitem(sys.modules, "tkinter", fake)
    monkeypatch.setitem(sys.modules, "tkinter.ttk", fake.ttk)
    monkeypatch.setitem(sys.modules, "tkinter.filedialog", fake.filedialog)
    monkeypatch.setitem(sys.modules, "tkinter.messagebox", fake.messagebox)
    return fake


def test_app_constructs_and_renders(tmp_path, fake_tk):
    from cert_data_process.app.gui import CertiApp

    app = CertiApp(runs_root=tmp_path)  # runs __init__ -> _build_* -> refresh_history

    # exercise the dynamic render paths (these build widgets at runtime)
    app.loaded_rec = None
    app._render_results()
    app.loaded_rec = {
        "name": "t", "status": "partial",
        "sigma": [
            {"corner": "ssgnp_0p450v_m40c", "type": "delay", "eBase": 100.0, "eW1": 100.0,
             "lBase": 93.2, "lW1": 96.0, "health": "OK", "total": 1180, "covered": 1180},
            {"corner": "ssgnp_0p450v_m40c", "type": "hold", "lBase": 91.5, "lW1": 91.5,
             "health": "OK", "total": 1261, "covered": 1261},
        ],
        "moments": [
            {"corner": "ssgnp_0p450v_m40c", "type": "delay", "ms": 99.1, "std": 97.4, "skew": 100.0,
             "msW1": 99.5, "stdW1": 98.0, "skewW1": 100.0, "health": "OK", "total": 1180, "covered": 1180},
        ],
        "config": {"vendor": "cdns", "process": "n2p", "process_version": "v0p9",
                   "corners": ["ssgnp_0p450v_m40c"], "types": ["delay", "hold"],
                   "fmc_golden_dir": "/x", "lib_dir": "/y"},
    }
    app._render_results()      # per-type colored grid + verdict
    app.basis = "w1"
    app._render_results()      # toggle path
    app._gather()              # config gather (mode routing)
    app._rerun_loaded()        # load config back into Setup
    app._mode_key()
