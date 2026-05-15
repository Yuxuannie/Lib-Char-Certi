import json

import pytest

from cert_data_process.cli import OUTPUT_DIRECTORIES, main


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
            "ssgnp_0p450v_m40c,ssgnp_0p465v_m40c",
            "--types",
            "delay,slew,hold,mpw",
            "--fmc-golden-dir",
            str(tmp_path / "fmc"),
            "--full-mc-golden-dir",
            str(tmp_path / "full_mc"),
            "--lib-dir",
            str(tmp_path / "libs"),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    for relative_dir in OUTPUT_DIRECTORIES:
        assert (output_dir / relative_dir).is_dir()

    run_manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["enabled_pipelines"] == ["sigma", "moments"]
    assert run_manifest["config"]["types"] == ["delay", "slew", "hold", "mpw"]
    assert run_manifest["aliases"] == []

    compatibility_report = json.loads((output_dir / "compatibility_report.json").read_text(encoding="utf-8"))
    assert compatibility_report["diffs"] == []
