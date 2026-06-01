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
    # new consolidated PR + outliers tabs (render with no runs -> empty paths)
    app._pr_records()
    app._render_pr_status()
    app._render_outliers()
    app._render_common()       # common-offenders tab (no runs -> empty)
    app.pr_basis = "base"
    app._render_pr_status()
    # audit banner + finding rendering under mocked tk
    app._audit_shown = 0
    from cert_data_process import audit as _audit
    sample = _audit.findings_to_dicts(
        [_audit.Finding("error", "lib_join_sigma", "no_lib", "no_lib_for_corner: X", "", "/l"),
         _audit.Finding("warn", "build_pr_table", "low_coverage", "LOW_COVERAGE 2780/66470 (4.2%)", "", "/l")])
    for s_name, items in {"lib_join_sigma": sample[:1], "build_pr_table": sample[1:]}.items():
        for text, tag in _audit.format_block(s_name, items):
            app._log(text, tag)
    # B3: exercise ranking + figure build headlessly (panel embedding needs a real display)
    import matplotlib; matplotlib.use("Agg")
    from cert_data_process.analysis import plots as _plots, outliers as _o
    pts = [(40.0, 38.0, True, "combinational_A_Z_rise_A_rise_NO_CONDITION_3_5")]
    assert _plots.build_scatter_figure(pts, "Late_Sigma", mode="abs_vs_rel", rel_threshold=0.03) is not None
    test_rows = [{"Arc": pts[0][3], "Late_Sigma_MC_value": "40",
                  "Late_Sigma_Lib_value": "38", "Late_Sigma_Final_Status": "Fail"}]
    assert _o.rank_by_cell(test_rows, "Late_Sigma")[0]["cell"] == "A"
    assert _o.arc_indices("combinational_A_Z_rise_A_rise_NO_CONDITION_3_5") == ("3", "5")
    tps = _o.rank_by_table_point(test_rows, "Late_Sigma")
    assert tps[0]["index1"] == "3" and tps[0]["index2"] == "5"
    # audit report access (no file -> info dialog path, mocked)
    assert app._audit_report_path() is None
    app._open_audit_report()
    # worst-arc detail popup (catches import-path / name errors in the handler)
    app._show_arc_detail(
        {"arc": "combinational_A_Z_rise_A_rise_NO_CONDITION_3_5", "cell": "A",
         "index1": "3", "index2": "5", "mc": 40.0, "lib": 38.0,
         "abs_err_ps": 2.0, "rel_pct": 5.0, "direction": "optimistic"},
        "Late_Sigma")
    # common-offenders "where it fails" matcher (per group-key)
    arc = "combinational_A_Z_rise_A_rise_NO_CONDITION_3_5"
    off = {"cell": "A", "arc": arc, "index1": "3", "index2": "5"}
    app._common_key = "cell"
    assert app._offender_matches(arc, off) is True
    app._common_key = "cell_arc"
    assert app._offender_matches(arc, off) is True
    assert app._offender_matches("combinational_B_Z_rise_A_rise_NO_CONDITION_3_5", off) is False
    app._common_key = "cell_table_point"
    assert app._offender_matches(arc, off) is True
    # Voltage Margin Analysis tab render paths (failed + ok), under mocked tk
    app._run_vm()  # no loaded_rec -> info dialog path, no crash
    app._render_vm({"ok": False, "reason": "no_sigma_rpt_inputs", "out_dir": "/x", "stderr_tail": "boom"})
    app._render_vm({
        "ok": True, "out_dir": "/x",
        "sensitivity_warnings": {"header": ["arc", "warning_code"],
                                 "rows": [["B", "voltage_gap_exceeds_max"]]},
        "summary": {"header": ["corner", "required_margin_mv"], "rows": [["c1", "12.3"]]},
        "per_object": {"header": ["arc", "required_margin_mv"], "rows": [["A", "5.0"]]},
        "optimistic_per_object": {"header": ["arc", "required_margin_mv"], "rows": [["A", "5.0"]]},
    })


def test_pr_status_and_outliers_render_with_a_real_record(tmp_path, fake_tk):
    from cert_data_process.app.gui import CertiApp
    from cert_data_process.web import runs

    rid = "b3_svt_20260601_000000"
    runs.write_run_record(tmp_path, rid, {
        "id": rid, "name": "B3 SVT", "batch_id": "B3",
        "config": {"vt_type": "svt", "library_type": "mb"},
        "sigma": [
            {"corner": "ssgnp_0p475v_0c", "type": "delay", "nomBase": 100.0, "nomW1": 100.0,
             "eBase": 100.0, "eW1": 100.0, "lBase": 92.59, "lW1": 92.7, "health": "OK"},
            {"corner": "ssgnp_0p475v_0c", "type": "hold", "nomBase": 100.0, "nomW1": 100.0,
             "lBase": 91.49, "lW1": 91.5, "health": "OK"},
        ],
        "moments": [
            {"corner": "ssgnp_0p475v_0c", "type": "delay", "ms": 99.6, "std": 99.9, "skew": 100.0,
             "msW1": 99.6, "stdW1": 99.9, "skewW1": 100.0, "health": "OK"},
        ],
    })
    runs.update_index(tmp_path, {"id": rid, "name": "B3 SVT", "when_utc": "2026-06-01T00:00:00"})

    app = CertiApp(runs_root=tmp_path)
    recs = app._pr_records()
    assert len(recs) == 1 and recs[0]["id"] == rid
    app._render_pr_status()    # builds the colored pivot grid from real data
    app._render_outliers()     # 92.59 / 91.49 are < 95 -> inserts outlier rows (no per-arc csv -> "?")


def test_compare_uses_all_metrics(tmp_path, fake_tk):
    from cert_data_process.app.gui import CertiApp
    from cert_data_process.web import runs

    def _rec(rid, bid, ldelay):
        return {"id": rid, "name": bid, "batch_id": bid,
                "config": {"vt_type": "svt", "library_type": "base"},
                "sigma": [{"corner": "c1", "type": "delay", "eBase": 100.0, "eW1": 100.0,
                           "lBase": ldelay, "lW1": ldelay, "health": "OK"}],
                "moments": [{"corner": "c1", "type": "delay", "ms": 99.0, "std": 98.0, "skew": 100.0,
                             "msW1": 99.0, "stdW1": 98.0, "skewW1": 100.0, "health": "OK"}]}

    for rid, bid, ld in (("r1", "B1", 92.0), ("r2", "B2", 88.0)):
        runs.write_run_record(tmp_path, rid, _rec(rid, bid, ld))
        runs.update_index(tmp_path, {"id": rid, "name": bid, "when_utc": f"2026-06-01T00:00:0{rid[-1]}"})

    app = CertiApp(runs_root=tmp_path)
    app._hist_checked = {"r1", "r2"}
    app._do_compare()          # exercises the full all-metrics cross-batch loop (no crash)
