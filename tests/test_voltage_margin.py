"""Voltage Margin integration runner (Phase A): command build + output parsing + guards."""

from cert_data_process.analysis import voltage_margin as vm


def test_build_cmd_includes_dirs_corners_and_valid_types(tmp_path):
    cmd = vm.build_cmd(tmp_path / "data", tmp_path / "out",
                       ["c1", "c2"], ["delay", "hold", "mpw"], tool_dir=tmp_path)
    assert cmd[0] == "python3" and cmd[1].endswith("run_analysis.py")
    assert "--output-dir" in cmd and "--corners" in cmd
    ts = cmd[cmd.index("--types") + 1:]
    assert "delay" in ts and "hold" in ts and "mpw" not in ts   # mpw not a VM type


def test_read_csv_rows(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("a,b\n1,2\n3,4\n")
    h, r = vm.read_csv_rows(p)
    assert h == ["a", "b"] and r == [["1", "2"], ["3", "4"]]
    assert vm.read_csv_rows(tmp_path / "missing.csv") == ([], [])


def test_read_outputs(tmp_path):
    (tmp_path / "all_errors").mkdir()
    (tmp_path / "sensitivity").mkdir()
    (tmp_path / "all_errors" / "margin_summary.csv").write_text("corner,required_margin_mv\nc1,12.3\n")
    (tmp_path / "all_errors" / "per_object_margin.csv").write_text("arc,required_margin_mv\nA,5.0\n")
    (tmp_path / "sensitivity" / "sensitivity_warnings.csv").write_text(
        "arc,warning_code\nB,voltage_gap_exceeds_max\n")
    out = vm.read_outputs(tmp_path)
    assert out["summary"]["rows"] == [["c1", "12.3"]]
    assert out["per_object"]["header"] == ["arc", "required_margin_mv"]
    assert out["sensitivity_warnings"]["rows"][0][1] == "voltage_gap_exceeds_max"


def test_run_guards_no_rpts_and_missing_tool(tmp_path):
    # missing tool dir
    r = vm.run_voltage_margin(tmp_path, ["c1"], ["delay"], tool_dir=tmp_path / "nope")
    assert r["ok"] is False and "vm_tool_not_found" in r["reason"]
    # tool present but no rpt inputs
    tool = tmp_path / "tool"; tool.mkdir()
    (tool / "run_analysis.py").write_text("# stub\n")
    (tmp_path / "combined" / "sigma").mkdir(parents=True)
    r2 = vm.run_voltage_margin(tmp_path, ["c1"], ["delay"], tool_dir=tool)
    assert r2["ok"] is False and "no_sigma_rpt_inputs" in r2["reason"]
