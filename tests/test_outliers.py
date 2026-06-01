"""outlier_breakdown: cells / polarity / worst-error from per-arc rows."""

from cert_data_process.analysis.outliers import outlier_breakdown


def _arc(cell, mc, lib, status):
    return {
        "Arc": f"combinational_{cell}_Z_rise_A_rise_NO_CONDITION_3_5",
        "Late_Sigma_MC_value": str(mc),
        "Late_Sigma_Lib_value": str(lib),
        "Late_Sigma_Final_Status": status,
    }


def test_outlier_breakdown_counts_cells_polarity_and_worst():
    rows = [
        _arc("INVD1", 40.0, 38.0, "Fail"),   # optimistic (lib<mc), abs 2.0, rel 5%
        _arc("INVD1", 40.0, 39.0, "Fail"),   # optimistic, same cell
        _arc("ND2D2", 50.0, 60.0, "Fail"),   # pessimistic (lib>mc), abs 10.0, rel 20%
        _arc("BUFD4", 30.0, 30.1, "Pass"),   # passing -> excluded
    ]
    r = outlier_breakdown(rows, "Late_Sigma")
    assert r["n_outlier_cells"] == 2
    assert r["worst_err_ps"] == 10.0
    assert round(r["worst_rel_pct"], 1) == 20.0
    assert r["polarity"] == "mixed"
    assert r["n_optimistic"] == 2 and r["n_pessimistic"] == 1


def test_outlier_breakdown_all_pass_is_empty():
    rows = [_arc("INVD1", 40.0, 40.0, "Pass")]
    r = outlier_breakdown(rows, "Late_Sigma")
    assert r["n_outlier_cells"] == 0
    assert r["worst_err_ps"] is None
    assert r["polarity"] == "none"
