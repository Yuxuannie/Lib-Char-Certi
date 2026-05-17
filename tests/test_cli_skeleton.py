import json

import pytest

from cert_data_process.cli import OUTPUT_DIRECTORIES, PLANNED_STAGE_STATUS, main


def _base_args(tmp_path, output_dir, *, types="delay,slew,hold,mpw"):
    return [
        "--vendor",
        "cdns",
        "--process",
        "n2p",
        "--process-version",
        "v1p0",
        "--corners",
        "ssgnp_0p450v_m40c,ssgnp_0p465v_m40c",
        "--types",
        types,
        "--lib-dir",
        str(tmp_path / "libs"),
        "--output-dir",
        str(output_dir),
    ]


def _run_dummy(tmp_path, *, fmc=False, full_mc=True, extra_args=None, types="delay,slew,hold,mpw"):
    output_dir = tmp_path / "results"
    args = _base_args(tmp_path, output_dir, types=types)
    if fmc:
        args.extend(["--fmc-golden-dir", str(tmp_path / "fmc")])
    if full_mc:
        args.extend(["--full-mc-golden-dir", str(tmp_path / "full_mc")])
    if extra_args:
        args.extend(extra_args)

    exit_code = main(args)
    run_manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    compatibility_report = json.loads((output_dir / "compatibility_report.json").read_text(encoding="utf-8"))
    return exit_code, output_dir, run_manifest, compatibility_report


def _write_hold_fixture(root):
    arc_dir = root / "ssgnp_0p450v_m40c_DECKS" / "hold" / "DECKS" / "hold_TESTCELL_D_rise_CP_rise_NO_CONDITION_1_1"
    arc_dir.mkdir(parents=True)
    (arc_dir / "summary1.csv").write_text("Nominal,Percentile LB,Percentile UB\n1e-12,0.7e-12,1.6e-12\n", encoding="utf-8")
    (arc_dir / "summary2.csv").write_text("Nominal,Percentile LB,Percentile UB\n2e-12,1.4e-12,3.2e-12\n", encoding="utf-8")


def test_help_runs(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--vendor" in captured.out
    assert "--fmc-golden-dir" in captured.out
    assert "--full-mc-golden-dir" in captured.out
    assert "--full-mc-keep-raw-samples" in captured.out


def test_dummy_run_materializes_output_tree(tmp_path):
    exit_code, output_dir, run_manifest, compatibility_report = _run_dummy(tmp_path)

    assert exit_code == 0
    for relative_dir in OUTPUT_DIRECTORIES:
        assert (output_dir / relative_dir).is_dir()

    assert run_manifest["enabled_pipelines"] == ["moments"]
    assert run_manifest["config"]["types"] == ["delay", "slew", "hold", "mpw"]
    assert run_manifest["aliases"] == []
    assert "tool_git_commit_sha" in run_manifest
    assert compatibility_report["diffs"] == []


def test_manifest_output_directories_matches_tuple(tmp_path):
    _, _, run_manifest, _ = _run_dummy(tmp_path)

    assert set(run_manifest["output_directories"]) == set(OUTPUT_DIRECTORIES)


def test_planned_stage_status_uses_unified_lib_join():
    lib_join_entries = [stage for stage in PLANNED_STAGE_STATUS if stage["stage"] == "lib_join"]

    assert lib_join_entries == [
        {
            "stage": "lib_join",
            "pipeline": "sigma,moments",
            "implemented": False,
            "planned_pr": "PR 4",
            "note": "Unified lib lookup core with sigma + moments output formatters",
        }
    ]


def test_both_golden_dirs_missing_errors(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        main(_base_args(tmp_path, tmp_path / "results"))

    assert exc_info.value.code == 2


def test_unsupported_type_errors(tmp_path):
    args = _base_args(tmp_path, tmp_path / "results")
    args[args.index("--types") + 1] = "setup"
    args.extend(["--fmc-golden-dir", str(tmp_path / "fmc")])

    with pytest.raises(SystemExit) as exc_info:
        main(args)

    assert exc_info.value.code == 2


def test_empty_corners_errors(tmp_path):
    args = _base_args(tmp_path, tmp_path / "results")
    args[args.index("--corners") + 1] = ",,,"
    args.extend(["--fmc-golden-dir", str(tmp_path / "fmc")])

    with pytest.raises(SystemExit) as exc_info:
        main(args)

    assert exc_info.value.code == 2


def test_invalid_vendor_errors(tmp_path):
    args = _base_args(tmp_path, tmp_path / "results")
    args[args.index("--vendor") + 1] = "xyz"
    args.extend(["--fmc-golden-dir", str(tmp_path / "fmc")])

    with pytest.raises(SystemExit) as exc_info:
        main(args)

    assert exc_info.value.code == 2


def test_sigma_only_pipeline_runs_fmc_combine_data(tmp_path):
    _write_hold_fixture(tmp_path / "fmc")
    output_dir = tmp_path / "results"
    args = [
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
        str(tmp_path / "fmc"),
        "--lib-dir",
        str(tmp_path / "libs"),
        "--output-dir",
        str(output_dir),
    ]

    assert main(args) == 0
    run_manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["enabled_pipelines"] == ["sigma"]
    assert run_manifest["config"]["run_sigma"] is True
    assert run_manifest["config"]["run_moments"] is False
    assert run_manifest["stage_execution"][0]["stage"] == "fmc_combine_data"
    assert run_manifest["stage_execution"][0]["status"] == "passed"
    assert (output_dir / "normalized" / "fmc" / "fmc_result_n2p_v1p0_ssgnp_0p450v_m40c_hold.csv").is_file()


def test_moments_only_pipeline_skips_fmc_combine_data(tmp_path):
    _, _, run_manifest, _ = _run_dummy(tmp_path, fmc=False, full_mc=True)

    assert run_manifest["enabled_pipelines"] == ["moments"]
    assert run_manifest["config"]["run_sigma"] is False
    assert run_manifest["config"]["run_moments"] is True
    assert run_manifest["stage_execution"] == []
