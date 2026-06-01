"""build_sigma_rows Nominal support + consolidate_pr multi-batch pivot."""

import csv

from cert_data_process.web.summary import build_sigma_rows
from cert_data_process.analysis.consolidate import PR_ROWS, pr_color, consolidate_pr


def test_build_sigma_rows_reads_nominal(tmp_path):
    d = tmp_path / "pr" / "sigma"
    d.mkdir(parents=True)
    f = d / "sigma_PR_table_with_waivers.csv"
    with f.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Corner", "Nominal_Base_PR", "Nominal_PR_with_Waiver1",
                    "Early_Sigma_Base_PR", "Early_Sigma_PR_with_Waiver1",
                    "Late_Sigma_Base_PR", "Late_Sigma_PR_with_Waiver1",
                    "Total_Arcs", "Covered", "Uncovered", "Coverage", "Data_Health", "Type"])
        w.writerow(["c1", "100.0%", "100.0%", "99.5%", "99.6%", "92.6%", "92.7%",
                    "1180", "1180", "0", "100.0%", "OK", "delay"])
    rows = build_sigma_rows(tmp_path)
    assert rows[0]["nomBase"] == 100.0 and rows[0]["nomW1"] == 100.0
    assert rows[0]["lBase"] == 92.6


def test_pr_color_bands():
    assert pr_color(100.0) == "green"
    assert pr_color(95.0) == "green"
    assert pr_color(94.9) == "amber"
    assert pr_color(90.0) == "amber"
    assert pr_color(89.9) == "red"
    assert pr_color(None) == "none"


def test_pr_rows_cover_all_slide_rows():
    labels = [r["label"] for r in PR_ROWS]
    assert labels == ["hold", "ocv_const_hold", "delay", "ocv_delay_early",
                      "ocv_delay_late", "delay_mns", "delay_skn", "delay_std",
                      "trans", "ocv_trans_early", "ocv_trans_late",
                      "trans_mns", "trans_skn", "trans_std"]


def _rec():
    return {
        "batch_id": "B3", "config": {"vt_type": "svt", "library_type": "mb"},
        "sigma": [
            {"corner": "ssgnp_0p475v_0c", "type": "delay", "nomBase": 100.0, "nomW1": 100.0,
             "eBase": 100.0, "eW1": 100.0, "lBase": 92.59, "lW1": 92.7, "health": "OK"},
            {"corner": "ssgnp_0p475v_0c", "type": "hold", "nomBase": 100.0, "nomW1": 100.0,
             "lBase": 91.49, "lW1": 91.5, "health": "OK"},
        ],
        "moments": [
            {"corner": "ssgnp_0p475v_0c", "type": "delay", "ms": 99.64, "std": 99.89, "skew": 100.0,
             "msW1": 99.64, "stdW1": 99.89, "skewW1": 100.0, "health": "OK"},
        ],
    }


def test_consolidate_builds_columns_and_cells():
    piv = consolidate_pr([_rec()], basis="w1")
    col = piv["columns"][0]
    assert col["batch_id"] == "B3" and col["vt"] == "svt" and col["libtype"] == "mb"
    assert col["corner"] == "ssgnp_0p475v_0c"
    cells = piv["cells"]
    assert cells[("ocv_delay_late", 0)]["pr"] == 92.7
    assert cells[("ocv_delay_late", 0)]["color"] == "amber"
    assert cells[("delay", 0)]["pr"] == 100.0 and cells[("delay", 0)]["color"] == "green"
    assert cells[("delay_skn", 0)]["pr"] == 100.0
    assert cells[("ocv_const_hold", 0)]["color"] == "amber"
