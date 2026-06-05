"""Input unit handling (lib_unit / fmc_unit): config, FMC scaling, lib-join arg.

Key invariants:
- defaults preserve current behavior exactly (SCLD ×1000, CDNS lib ×1, SNPS lib ×1000),
- Skew is dimensionless and NEVER scaled.
"""

import csv

from cert_data_process.config import build_config, unit_factor, UNIT_TO_PS
from cert_data_process.parsers import fmc_scld_adapter as A
from cert_data_process.stages.lib_join_sigma import _build_liberate_cmd


def test_unit_factor_and_config(tmp_path):
    assert unit_factor("ns") == 1000.0 and unit_factor("ps") == 1.0
    assert unit_factor("us") == 1_000_000.0 and unit_factor("") == 1.0
    cfg = build_config(
        vendor="cdns", process="n2p", process_version="v1p0",
        corners=["c"], types=["delay"], lib_dir=str(tmp_path), output_dir=str(tmp_path / "o"),
        fmc_golden_dir=str(tmp_path), lib_unit="NS ", fmc_unit="bogus")
    assert cfg.lib_unit == "ns"          # trimmed/lowered
    assert cfg.fmc_unit == ""            # invalid dropped -> default
    assert cfg.to_manifest_dict()["lib_unit"] == "ns"


# ---- SCLD adapter scale is parametrized; default preserves ×1000 ----
_DELAY_HDR = [
    "PVT", "Cell", "pin", "rel_pin", "pin_dir", "rel_pin_dir", "when", "point", "type",
    "index_1", "index_2", "nominal(ns)",
    "ocv_early_sigma_lb(ns)", "ocv_early_sigma(ns)", "ocv_early_sigma_ub(ns)",
    "ocv_late_sigma_lb(ns)", "ocv_late_sigma(ns)", "ocv_late_sigma_ub(ns)",
    "ocv_mean_shift_lb(ns)", "ocv_mean_shift(ns)", "ocv_mean_shift_ub(ns)",
    "ocv_std_dev_lb(ns)", "ocv_std_dev(ns)", "ocv_std_dev_ub(ns)",
    "ocv_skewness_lb(ns)", "ocv_skewness(ns)", "ocv_skewness_ub(ns)", "tool", "deck",
]


def _delay_file(tmp_path):
    p = tmp_path / "delay_x.csv"
    row = ["ssgnp", "INVD1", "Z", "A", "rise", "rise", "E&!TE", "3;5", "delay", "0.07", "0.01",
           "0.035", "0.0001", "0.046", "0.00076", "0.0002", "0.041", "0.00075",
           "0.000001", "0.00003", "0.000005", "0.0008", "0.085", "0.0009",
           "-1.27", "0.07", "1.18", "fmc", "/d"]
    with p.open("w", newline="") as fh:
        w = csv.writer(fh); w.writerow(_DELAY_HDR); w.writerow(row)
    return p


def test_scld_default_scale_is_ns_to_ps_and_skew_unscaled(tmp_path):
    by_type, _ = A.adapt_scld_file(_delay_file(tmp_path))   # default value_scale = NS_TO_PS
    d = dict(zip(A.DELAY_SLEW_HEADER, by_type["delay"][0]))
    assert d["MC_Nominal"] == 35.0          # 0.035 ns -> ps
    assert d["MC_Std"] == 85.0              # 0.085 ns -> ps
    assert d["MC_Skew"] == 0.07             # skew NEVER scaled


def test_scld_value_scale_ps_keeps_raw(tmp_path):
    by_type, _ = A.adapt_scld_file(_delay_file(tmp_path), value_scale=1.0)  # user says ps
    d = dict(zip(A.DELAY_SLEW_HEADER, by_type["delay"][0]))
    assert d["MC_Nominal"] == 0.035         # not multiplied
    assert d["MC_Skew"] == 0.07             # skew still unscaled


def test_scale_normalized_mc_skips_skew(tmp_path):
    p = tmp_path / "n.csv"
    header = ["Arc", "MC_Nominal", "MC_Late_Sigma", "MC_Skew", "first_index"]
    with p.open("w", newline="") as fh:
        csv.writer(fh).writerows([header, ["a", "0.035", "0.046", "0.07", "3"]])
    A.scale_normalized_mc(p, 1000.0)
    rows = list(csv.reader(p.open()))
    got = dict(zip(rows[0], rows[1]))
    assert float(got["MC_Nominal"]) == 35.0 and float(got["MC_Late_Sigma"]) == 46.0
    assert float(got["MC_Skew"]) == 0.07    # skew untouched
    assert got["first_index"] == "3"        # non-MC untouched


def test_scale_normalized_mc_noop_when_factor_one(tmp_path):
    p = tmp_path / "n.csv"
    with p.open("w", newline="") as fh:
        csv.writer(fh).writerows([["Arc", "MC_Nominal"], ["a", "0.035"]])
    A.scale_normalized_mc(p, 1.0)
    assert list(csv.reader(p.open()))[1] == ["a", "0.035"]


def test_lib_join_unit_change_arg():
    from pathlib import Path
    base = dict(tcl=Path("t"), script=Path("s"), lib_file=Path("l"), csv_path=Path("c"), mode="Delay")
    assert "-unit_change" not in _build_liberate_cmd(**base)                  # unset -> vendor default
    cmd = _build_liberate_cmd(**base, unit_change=1000.0)
    assert "-unit_change" in cmd and cmd[cmd.index("-unit_change") + 1] == repr(1000.0)
