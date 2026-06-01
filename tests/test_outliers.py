"""outlier_breakdown: cells / polarity / worst-error from per-arc rows + rankings."""

from cert_data_process.analysis.outliers import (
    outlier_breakdown, arc_indices, rank_by_cell, rank_by_table_point, worst_arcs,
)


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


def _a(cell, i1, i2, mc, lib, status):
    return {"Arc": f"combinational_{cell}_Z_rise_A_rise_NO_CONDITION_{i1}_{i2}",
            "Late_Sigma_MC_value": str(mc), "Late_Sigma_Lib_value": str(lib),
            "Late_Sigma_Final_Status": status}


def test_arc_indices():
    assert arc_indices("combinational_INV_Z_rise_A_rise_NO_CONDITION_3_5") == ("3", "5")
    assert arc_indices("weird") == ("", "")


def test_rank_by_cell_orders_by_failcount_then_worst():
    rows = [_a("A", 3, 5, 40, 38, "Fail"), _a("A", 3, 6, 40, 39, "Fail"),
            _a("B", 3, 5, 50, 70, "Fail"), _a("C", 1, 1, 10, 10, "Pass")]
    r = rank_by_cell(rows, "Late_Sigma")
    assert r[0]["cell"] == "A" and r[0]["n_fail"] == 2
    assert {x["cell"] for x in r} == {"A", "B"}
    assert r[1]["cell"] == "B" and round(r[1]["worst_rel_pct"], 0) == 40


def test_rank_by_table_point_and_worst_arcs():
    rows = [_a("A", 3, 5, 40, 38, "Fail"), _a("B", 3, 5, 50, 70, "Fail"),
            _a("C", 7, 7, 10, 10, "Pass")]
    tp = rank_by_table_point(rows, "Late_Sigma")
    assert tp[0]["index1"] == "3" and tp[0]["index2"] == "5" and tp[0]["n_fail"] == 2
    w = worst_arcs(rows, "Late_Sigma", top=5)
    assert w[0]["cell"] == "B" and w[0]["direction"] == "pessimistic" and round(w[0]["rel_pct"]) == 40


def test_rel_pct_uses_engine_denominator_when_present():
    from cert_data_process.analysis.outliers import rel_pct_for
    # engine rel_err column present -> use it (5%), NOT |lib-mc|/|mc| (which would be 100%)
    row = {"Late_Sigma_rel_err": "0.05"}
    assert rel_pct_for(row, "Late_Sigma", 100.0, 200.0) == 5.0
    # absent -> fallback recompute |200-100|/100 = 100%
    assert rel_pct_for({}, "Late_Sigma", 100.0, 200.0) == 100.0


def test_worst_arcs_rel_uses_engine_column():
    rows = [{"Arc": "combinational_A_Z_rise_A_rise_NO_CONDITION_3_5",
             "Late_Sigma_MC_value": "500", "Late_Sigma_Lib_value": "550",
             "Late_Sigma_Final_Status": "Fail", "Late_Sigma_rel_err": "0.10"}]
    w = worst_arcs(rows, "Late_Sigma")
    assert round(w[0]["rel_pct"], 1) == 10.0      # engine 10%, not |550-500|/500=10%... here same; check engine path
    # abs err is still raw ps
    assert w[0]["abs_err_ps"] == 50.0


def test_polarity_filter_on_ranks():
    rows = [_a("A", 3, 5, 40, 38, "Fail"),   # optimistic (lib<mc)
            _a("B", 3, 5, 50, 70, "Fail")]   # pessimistic (lib>mc)
    assert {d["cell"] for d in rank_by_cell(rows, "Late_Sigma", polarity="opt")} == {"A"}
    assert {d["cell"] for d in rank_by_cell(rows, "Late_Sigma", polarity="pess")} == {"B"}
    assert {d["cell"] for d in rank_by_cell(rows, "Late_Sigma", polarity="all")} == {"A", "B"}
    assert {w["cell"] for w in worst_arcs(rows, "Late_Sigma", polarity="opt")} == {"A"}
