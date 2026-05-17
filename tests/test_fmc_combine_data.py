import json

from cert_data_process.cli import main


def test_fmc_combine_data_hold_writes_csv_with_crlf_and_largest_summary(tmp_path):
    fmc_root = tmp_path / "gen_DECKs"
    arc_dir = fmc_root / "ssgnp_0p450v_m40c_DECKS" / "hold" / "DECKS" / "hold_TESTCELL_D_rise_CP_rise_NO_CONDITION_1_1"
    arc_dir.mkdir(parents=True)
    (arc_dir / "summary1.csv").write_text("Nominal,Percentile LB,Percentile UB\n1e-12,0.7e-12,1.6e-12\n", encoding="utf-8")
    (arc_dir / "summary2.csv").write_text("Nominal,Percentile LB,Percentile UB\n2e-12,1.4e-12,3.2e-12\n", encoding="utf-8")

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
            "hold",
            "--fmc-golden-dir",
            str(fmc_root),
            "--lib-dir",
            str(tmp_path / "libs"),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    output_csv = output_dir / "normalized" / "fmc" / "fmc_result_n2p_v1p0_ssgnp_0p450v_m40c_hold.csv"
    content = output_csv.read_bytes()
    assert b"\r\n" in content
    assert b"2.0,0.10000000000000006,0.4000000000000001,-0.19999999999999996" in content

    run_manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["stage_execution"][0]["processed"][0]["arc_count_processed"] == 1


def test_fmc_combine_data_missing_requested_corner_reports_failure(tmp_path):
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
            "delay",
            "--fmc-golden-dir",
            str(tmp_path / "missing_gen_DECKs"),
            "--lib-dir",
            str(tmp_path / "libs"),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 1
    run_manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    stage = run_manifest["stage_execution"][0]
    assert stage["status"] == "failed"
    assert stage["failures"][0]["reason"] == "missing_corner_dir"
