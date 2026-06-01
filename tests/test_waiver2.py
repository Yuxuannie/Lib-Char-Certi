"""Waiver_2 (abs_tol, hold Late_Sigma only): config carrier + pure PR recompute."""

from cert_data_process.config import build_config


def test_config_carries_abs_tol_by_corner(tmp_path):
    cfg = build_config(
        vendor="cdns", process="n2p", process_version="v1p0",
        corners=["ssgnp_0p475v_0c", "ssgnp_0p515v_0c"], types=["hold"],
        lib_dir=str(tmp_path), output_dir=str(tmp_path / "out"),
        fmc_mode="parsed_scld", fmc_input_dir=str(tmp_path),
        abs_tol_ps_by_corner={"ssgnp_0p475v_0c": 19.5},
    )
    assert cfg.abs_tol_ps_by_corner == {"ssgnp_0p475v_0c": 19.5}
    m = cfg.to_manifest_dict()
    assert m["abs_tol_ps_by_corner"] == {"ssgnp_0p475v_0c": 19.5}


def test_config_abs_tol_defaults_empty(tmp_path):
    cfg = build_config(
        vendor="cdns", process="n2p", process_version="v1p0",
        corners=["c"], types=["hold"],
        lib_dir=str(tmp_path), output_dir=str(tmp_path / "out"),
        fmc_golden_dir=str(tmp_path),
    )
    assert cfg.abs_tol_ps_by_corner == {}


def test_config_abs_tol_drops_nonpositive_and_blank(tmp_path):
    cfg = build_config(
        vendor="cdns", process="n2p", process_version="v1p0",
        corners=["c"], types=["hold"],
        lib_dir=str(tmp_path), output_dir=str(tmp_path / "out"),
        fmc_golden_dir=str(tmp_path),
        abs_tol_ps_by_corner={" c1 ": "19.5", "c2": 0, "": 5, "c3": "bad"},
    )
    assert cfg.abs_tol_ps_by_corner == {"c1": 19.5}  # trimmed; 0/blank/non-numeric dropped


# ---- pure W2 recompute over per-arc hold rows ----
from cert_data_process.analysis.waivers import hold_abs_tol_pr


def _hold(mc, lib, base, w1, covered=True):
    return {"Late_Sigma_MC_value": str(mc), "Late_Sigma_Lib_value": str(lib),
            "Late_Sigma_Base_Pass": "N/A" if not covered else base,
            "Late_Sigma_Waiver1_CI_Enlarged": "N/A" if not covered else w1}


def test_hold_abs_tol_pr_stacks_on_base_and_w1():
    rows = [
        _hold(100, 100, "Pass", "Pass"),    # base pass
        _hold(100, 130, "Fail", "Pass"),    # w1 pass
        _hold(100, 110, "Fail", "Fail"),    # |dif|=10 <= 19.5 -> waived by W2
        _hold(100, 140, "Fail", "Fail"),    # |dif|=40 > 19.5 -> fails all
        _hold(0, 0, "Fail", "Fail", covered=False),  # uncovered -> excluded
    ]
    r = hold_abs_tol_pr(rows, 19.5)
    assert r["covered"] == 4
    assert r["base_pr"] == 25.0          # 1/4
    assert r["pr_w1"] == 50.0            # 2/4
    assert r["pr_w2"] == 75.0            # 3/4
    assert r["n_waived_by_w2"] == 1      # only arc3 newly waived


def test_hold_abs_tol_pr_zero_tol_equals_w1():
    rows = [_hold(100, 110, "Fail", "Fail")]   # would be waived only if tol>=10
    r = hold_abs_tol_pr(rows, 0.0)
    assert r["pr_w2"] == r["pr_w1"] == 0.0
    assert r["n_waived_by_w2"] == 0


# ---- GUI abs_tol entry parsing ----
from cert_data_process.app.gui import _parse_abs_tol


def test_parse_abs_tol_single_value_applies_to_all_corners():
    assert _parse_abs_tol("19.5", ["c1", "c2"]) == {"c1": 19.5, "c2": 19.5}


def test_parse_abs_tol_per_corner():
    assert _parse_abs_tol("c1=19.5, c2=20", ["c1", "c2"]) == {"c1": 19.5, "c2": 20.0}


def test_parse_abs_tol_blank_and_bad():
    assert _parse_abs_tol("", ["c1"]) == {}
    assert _parse_abs_tol("oops", ["c1"]) == {}
    assert _parse_abs_tol("c1=-5", ["c1"]) == {}   # non-positive dropped


# ---- consolidate w2 basis ----
from cert_data_process.analysis.consolidate import _value


def test_consolidate_w2_uses_lW2_for_hold_late_sigma():
    hold = {"lBase": 91.0, "lW1": 91.5, "lW2": 99.0}
    assert _value("Late_Sigma", "w2", hold, None) == 99.0
    assert _value("Late_Sigma", "w1", hold, None) == 91.5
    # no lW2 present -> w2 falls back to w1
    assert _value("Late_Sigma", "w2", {"lBase": 91.0, "lW1": 91.5}, None) == 91.5
