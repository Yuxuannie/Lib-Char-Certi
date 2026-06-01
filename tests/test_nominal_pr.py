"""Nominal PR support in check_sigma_with_waivers (rel-error-only, no CI bounds)."""

import importlib.util
import pathlib

import pandas as pd

_SPEC = importlib.util.spec_from_file_location(
    "check_sigma_ww",
    pathlib.Path("2-data_process/get_PR/Sigma/check_sigma_with_waivers.py"),
)
csm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(csm)  # safe: main() runs only under __main__ guard


def _row(**kw):
    base = {"Arc": "combinational_INVD1_Z_rise_A_rise_NO_CONDITION_3_5"}
    base.update(kw)
    return pd.Series(base)


def test_nominal_pass_uses_rel_error_only_when_no_ci_columns():
    row = _row(MC_Nominal=100.0, CDNS_Lib_Nominal=100.5)  # 0.5% off, no CI cols
    r = csm.check_pass_with_waivers(row, "delay", "Nominal", lib_prefix="CDNS_Lib")
    assert r["covered"] is True
    assert r["base_pass"] is True            # 0.5% <= 3% delay threshold
    assert r["waiver1_ci_enlarged"] is True  # no CI -> waiver1 falls back to rel pass


def test_nominal_fail_when_rel_error_exceeds_threshold():
    row = _row(MC_Nominal=100.0, CDNS_Lib_Nominal=110.0)  # 10% off
    r = csm.check_pass_with_waivers(row, "delay", "Nominal", lib_prefix="CDNS_Lib")
    assert r["covered"] is True
    assert r["base_pass"] is False
    assert r["waiver1_ci_enlarged"] is False


def test_sigma_still_uses_ci_bounds():
    # lib outside rel threshold but inside CI -> base pass via CI (unchanged behavior)
    row = _row(MC_Late_Sigma=100.0, CDNS_Lib_Late_Sigma=120.0,
               MC_Late_Sigma_LB=90.0, MC_Late_Sigma_UB=130.0)
    r = csm.check_pass_with_waivers(row, "delay", "Late_Sigma", lib_prefix="CDNS_Lib")
    assert r["covered"] is True
    assert r["base_pass"] is True
    assert r["pass_reason"] == "ci_bounds"
