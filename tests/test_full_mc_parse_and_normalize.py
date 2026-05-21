import json

from cert_data_process.cli import main


def test_full_mc_parse_and_normalize_moments_only(tmp_path):
    full_mc_root = tmp_path / "full_mc"
    arc_dir = full_mc_root / "ssgnp_0p450v_m40c" / "combinational_TESTCELL_Z_rise_A_rise_NO_CONDITION_1_1"
    arc_dir.mkdir(parents=True)

    (arc_dir / "mc_sim.sp").write_text(
        """
* test
.param cl = 2e-15
.param rel_pin_slew = 3e-12
* TEMPLATE_DECK
""".strip()
        + "\n",
        encoding="utf-8",
    )

    (arc_dir / "OUT.ava.report").write_text(
        """
##Sample_Moments
half_tt_out meas_delay meas_tt_out
Nominal 1e-12 2e-12 3e-12
Stddev 0.0 0.1e-12 0.2e-12
Skewness 0.0 0.7 0.8
##Response_Correlation_Matrix
""".strip()
        + "\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "results"
    exit_code = main(
        [
            "--vendor",
            "cdns",
            "--process",
            "n2p",
            "--process-version",
            "v1p0",
            "--corners",
            "ssgnp_0p450v_m40c",
            "--types",
            "delay,slew",
            "--full-mc-golden-dir",
            str(full_mc_root),
            "--lib-dir",
            str(tmp_path / "libs"),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    delay_csv = output_dir / "normalized" / "full_mc" / "fmc_result_n2p_v1p0_ssgnp_0p450v_m40c_delay.csv"
    slew_csv = output_dir / "normalized" / "full_mc" / "fmc_result_n2p_v1p0_ssgnp_0p450v_m40c_slew.csv"
    mc_delay_csv = output_dir / "normalized" / "full_mc" / "MC_n2p_v1p0_ssgnp_0p450v_m40c_delay.csv"
    mc_slew_csv = output_dir / "normalized" / "full_mc" / "MC_n2p_v1p0_ssgnp_0p450v_m40c_slew.csv"
    assert delay_csv.is_file()
    assert slew_csv.is_file()
    assert mc_delay_csv.is_file()
    assert mc_slew_csv.is_file()

    layer_a_csv = output_dir / "debug" / "full_mc" / "combinational_TESTCELL_Z_rise_A_rise_NO_CONDITION_1_1" / "stats_legacy_shape.csv"
    assert layer_a_csv.is_file()
    text = layer_a_csv.read_text(encoding="utf-8")
    assert "half_tt_out,meas_delay,meas_tt_out" in text

    manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["enabled_pipelines"] == ["moments"]
    assert manifest["stage_execution"][0]["stage"] == "full_mc_parse_and_normalize"
    assert manifest["stage_execution"][0]["layer_a_artifacts_count"] == 1
    assert manifest["stage_execution"][0]["layer_b_artifacts_count"] == 2
    assert manifest["stage_execution"][0]["mc_golden_artifacts_count"] == 2
