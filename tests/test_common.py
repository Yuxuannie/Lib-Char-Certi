"""Common-offenders: cross-context outlier commonality (cell / cell+arc / cell+table_point)."""

from cert_data_process.analysis.common import common_offenders


def _row(cell, i1, i2, mc, lib, status="Fail"):
    return {"Arc": f"combinational_{cell}_Z_rise_A_rise_NO_CONDITION_{i1}_{i2}",
            "Late_Sigma_MC_value": str(mc), "Late_Sigma_Lib_value": str(lib),
            "Late_Sigma_Final_Status": status}


def _data():
    return {
        ("B1", "c1"): [_row("A", 3, 5, 40, 38), _row("B", 3, 5, 50, 70)],
        ("B1", "c2"): [_row("A", 3, 5, 40, 37), _row("C", 1, 1, 10, 10, "Pass")],
    }


def test_by_cell_ranks_multi_context_first():
    res = common_offenders(_data(), "Late_Sigma", key="cell")
    assert res[0]["cell"] == "A"
    assert res[0]["n_contexts"] == 2
    assert sorted(res[0]["contexts"]) == [("B1", "c1"), ("B1", "c2")]
    assert res[0]["polarity"] == "optimistic"      # both A rows lib<mc
    assert round(res[0]["worst_rel_pct"]) == 8      # 3/40 = 7.5 -> 8
    # B fails in one context only; C passed -> excluded
    assert {r["cell"] for r in res} == {"A", "B"}
    assert next(r for r in res if r["cell"] == "B")["n_contexts"] == 1


def test_by_cell_arc_groups_full_arc():
    res = common_offenders(_data(), "Late_Sigma", key="cell_arc")
    a = next(r for r in res if r["cell"] == "A")
    assert a["n_contexts"] == 2                     # identical arc string in both contexts
    assert a["arc"].endswith("_3_5")


def test_by_cell_table_point():
    res = common_offenders(_data(), "Late_Sigma", key="cell_table_point")
    a = next(r for r in res if r["cell"] == "A")
    assert a["index1"] == "3" and a["index2"] == "5"
    assert a["n_contexts"] == 2


def test_empty_input():
    assert common_offenders({}, "Late_Sigma", key="cell") == []
