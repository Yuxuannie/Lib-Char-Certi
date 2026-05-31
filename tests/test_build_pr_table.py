from pathlib import Path

from cert_data_process.config import CertDataProcessConfig
from cert_data_process.stages.get_pr_sigma import run_build_pr_table


def test_build_pr_table_uses_absolute_script_and_root_paths(tmp_path, monkeypatch):
    output_dir = tmp_path / "out"
    root_path = output_dir / "combined" / "sigma"
    root_path.mkdir(parents=True)
    (root_path / "example_fmc_result.rpt").write_text("dummy\n", encoding="utf-8")

    captured = {}

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd, *, cwd, capture_output, text):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["capture_output"] = capture_output
        captured["text"] = text
        return Completed()

    monkeypatch.setattr("cert_data_process.stages.get_pr_sigma.subprocess.run", fake_run)

    config = CertDataProcessConfig(
        vendor="cdns",
        process="n2p",
        process_version="v1.0",
        corners=("ssgnp_0p450v_m40c",),
        types=("delay",),
        lib_dir=tmp_path / "libs",
        output_dir=output_dir,
        fmc_golden_dir=tmp_path / "fmc",
    )

    result = run_build_pr_table(config)

    assert result.stage_execution["status"] == "passed"
    assert Path(captured["cmd"][1]).is_absolute()
    assert captured["cmd"][1].endswith("2-data_process/get_PR/Sigma/check_sigma_with_waivers.py")
    root_arg = captured["cmd"][captured["cmd"].index("--root_path") + 1]
    assert Path(root_arg).is_absolute()
    assert captured["cwd"] == str(Path(__file__).resolve().parents[1])
    assert captured["capture_output"] is True
    assert captured["text"] is True
