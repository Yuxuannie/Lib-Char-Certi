import json

import pytest

from cert_data_process.cli import OUTPUT_DIRECTORIES, PLANNED_STAGE_STATUS, main


def _base_args(tmp_path, output_dir):
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
        "delay,slew,hold,mpw",
        "--lib-dir",
        str(tmp_path / "libs"),
        "--output-dir",
        str(output_dir),
    ]


def _run_dummy(tmp_path, *, fmc=True, full_mc=True, extra_args=None):
    output_dir = tmp_path / "results"
    args = _base_args(tmp_path, output_dir)
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

    assert run_manifest["enabled_pipelines"] == ["sigma", "moments"]
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


def test_sigma_only_pipeline(tmp_path):
    _, _, run_manifest, _ = _run_dummy(tmp_path, fmc=True, full_mc=False)

    assert run_manifest["enabled_pipelines"] == ["sigma"]
    assert run_manifest["config"]["run_sigma"] is True
    assert run_manifest["config"]["run_moments"] is False


def test_moments_only_pipeline(tmp_path):
    _, _, run_manifest, _ = _run_dummy(tmp_path, fmc=False, full_mc=True)

    assert run_manifest["enabled_pipelines"] == ["moments"]
    assert run_manifest["config"]["run_sigma"] is False
    assert run_manifest["config"]["run_moments"] is True
