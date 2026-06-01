"""perarc: locate per-arc CSVs + extract scatter points."""

import csv

from cert_data_process.analysis import perarc


def test_metric_source():
    assert perarc.metric_source("Late_Sigma") == "sigma"
    assert perarc.metric_source("Nominal") == "sigma"
    assert perarc.metric_source("Std") == "moments"


def _write(path, header, rows):
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def test_find_per_arc_csv_routes_by_metric(tmp_path):
    d = tmp_path / "combined" / "sigma"
    d.mkdir(parents=True)
    sig = d / "fmc_result_n2p_v1p0_ssgnp_0p475v_0c_hold_fmc_cdns_lib_comp_sigma_check_with_waivers.csv"
    mom = d / "fmc_result_n2p_v1p0_ssgnp_0p475v_0c_delay_fmc_cdns_lib_comp_moments_check.csv"
    sig.write_text("Arc\n"); mom.write_text("Arc\n")

    got = perarc.find_per_arc_csv(tmp_path, "ssgnp_0p475v_0c", "hold", "Late_Sigma")
    assert got == sig
    got2 = perarc.find_per_arc_csv(tmp_path, "ssgnp_0p475v_0c", "delay", "Std")
    assert got2 == mom
    assert perarc.find_per_arc_csv(tmp_path, "nope", "hold", "Late_Sigma") is None


def test_scatter_points(tmp_path):
    rows = [
        {"Arc": "combinational_INVD1_Z_rise_A_rise_NO_CONDITION_3_5",
         "Late_Sigma_MC_value": "40", "Late_Sigma_Lib_value": "38", "Late_Sigma_Final_Status": "Fail"},
        {"Arc": "combinational_BUFD4_Z_rise_A_rise_NO_CONDITION_3_5",
         "Late_Sigma_MC_value": "30", "Late_Sigma_Lib_value": "30", "Late_Sigma_Final_Status": "Pass"},
        {"Arc": "x", "Late_Sigma_MC_value": "", "Late_Sigma_Lib_value": "", "Late_Sigma_Final_Status": ""},
    ]
    pts = perarc.scatter_points(rows, "Late_Sigma")
    assert len(pts) == 2                       # blank-value row dropped
    assert pts[0] == (40.0, 38.0, True, "combinational_INVD1_Z_rise_A_rise_NO_CONDITION_3_5")
    assert pts[1][2] is False                  # passing arc not an outlier
