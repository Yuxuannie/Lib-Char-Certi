"""Tests for the SCLD -> normalized FMC adapter (pure, no liberate/display)."""

import csv

from cert_data_process.parsers import fmc_scld_adapter as A

_DELAY_HDR = [
    "PVT", "Cell", "pin", "rel_pin", "pin_dir", "rel_pin_dir", "when", "point", "type",
    "index_1", "index_2", "nominal(ns)",
    "ocv_early_sigma_lb(ns)", "ocv_early_sigma(ns)", "ocv_early_sigma_ub(ns)",
    "ocv_late_sigma_lb(ns)", "ocv_late_sigma(ns)", "ocv_late_sigma_ub(ns)",
    "ocv_mean_shift_lb(ns)", "ocv_mean_shift(ns)", "ocv_mean_shift_ub(ns)",
    "ocv_std_dev_lb(ns)", "ocv_std_dev(ns)", "ocv_std_dev_ub(ns)",
    "ocv_skewness_lb(ns)", "ocv_skewness(ns)", "ocv_skewness_ub(ns)", "tool", "deck",
]
_CONS_HDR = [
    "PVT", "Cell", "pin", "rel_pin", "pin_dir", "rel_pin_dir", "when", "point", "type",
    "index_1", "index_2", "nominal(ns)",
    "ocv_late_sigma_lb(ns)", "ocv_late_sigma(ns)", "ocv_late_sigma_ub(ns)", "tool", "deck",
]


def _delay_row(typ, pdir, when, point="3;5"):
    return ["ssgnp", "INVD1", "Z", "A", pdir, "rise", when, point, typ, "0.0728", "0.0107",
            "0.035", "0.0001", "0.046", "0.00076", "0.0002", "0.041", "0.00075",
            "0.000001", "0.00003", "0.000005", "0.0008", "0.085", "0.0009",
            "-1.27", "0.07", "1.18", "fmc", "/decks/x"]


def _cons_row(typ, pdir, point="2;3"):
    return ["ssgnp", "DFF", "D", "CP", pdir, "rise", "SE&!SI", point, typ, "0.05", "0.01",
            "0.5", "0.001", "0.066", "0.002", "fmc", "/d"]


def _write(tmp_path, name, header, rows):
    p = tmp_path / name
    with p.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return p


def test_delay_file_splits_into_delay_and_slew(tmp_path):
    f = _write(tmp_path, "delay_x.csv", _DELAY_HDR,
               [_delay_row("delay", "rise", "E&!TE"), _delay_row("slew", "fall", "NO_CONDITION")])
    by_type, warnings = A.adapt_scld_file(f)
    assert set(by_type) == {"delay", "slew"}
    assert not warnings
    d = dict(zip(A.DELAY_SLEW_HEADER, by_type["delay"][0]))
    assert d["MC_Nominal"] == 35.0          # 0.035 ns -> ps
    assert d["MC_Early_Sigma"] == 46.0      # 0.046 ns -> ps
    assert d["MC_Std"] == 85.0              # 0.085 ns -> ps
    assert d["MC_Skew"] == 0.07             # dimensionless, unscaled
    assert d["Table_Type"] == "cell_rise"
    assert d["Arc"] == "combinational_INVD1_Z_rise_A_rise_E_notTE_3_5"
    assert d["first_index"] == "3" and d["sec_index"] == "5"
    s = dict(zip(A.DELAY_SLEW_HEADER, by_type["slew"][0]))
    assert s["Table_Type"] == "fall_transition"
    assert s["Arc"].endswith("_NO_CONDITION_3_5")


def test_cons_file_splits_into_hold_and_mpw(tmp_path):
    f = _write(tmp_path, "cons_x.csv", _CONS_HDR,
               [_cons_row("hold", "rise"), _cons_row("min_pulse_width", "fall")])
    by_type, _ = A.adapt_scld_file(f)
    assert set(by_type) == {"hold", "mpw"}
    h = dict(zip(A.HOLD_MPW_HEADER, by_type["hold"][0]))
    assert h["MC_Late_Sigma"] == 66.0       # 0.066 ns -> ps
    assert h["Table_Type"] == "rise_constraint"
    m = dict(zip(A.HOLD_MPW_HEADER, by_type["mpw"][0]))
    assert m["Arc"].startswith("mpw_DFF_")   # single-token prefix for lib-join parse


def test_unknown_type_is_reported_and_skipped(tmp_path):
    f = _write(tmp_path, "delay_x.csv", _DELAY_HDR,
               [_delay_row("delay", "rise", "NO_CONDITION"), _delay_row("recovery", "rise", "x")])
    by_type, warnings = A.adapt_scld_file(f)
    assert set(by_type) == {"delay"}
    assert any("recovery" in w for w in warnings)


def test_write_normalized_roundtrip(tmp_path):
    f = _write(tmp_path, "delay_x.csv", _DELAY_HDR, [_delay_row("delay", "rise", "NO_CONDITION")])
    by_type, _ = A.adapt_scld_file(f)
    out = A.write_normalized(tmp_path / "norm", "n2p_v0p9", "ssgnp_0p475v_0c", "delay", by_type["delay"])
    assert out.name == "fmc_result_n2p_v0p9_ssgnp_0p475v_0c_delay.csv"
    rows = list(csv.reader(out.open()))
    assert rows[0] == A.DELAY_SLEW_HEADER
    assert len(rows) == 2
