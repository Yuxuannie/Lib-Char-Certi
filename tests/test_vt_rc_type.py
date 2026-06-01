"""VT/RC type: config pass-through + parsed-file disambiguation filter."""

from pathlib import Path

from cert_data_process.config import build_config
from cert_data_process.stages.fmc_ingest_parsed import _apply_vtrc


def test_config_carries_vt_rc(tmp_path):
    cfg = build_config(
        vendor="cdns", process="n2p", process_version="v0p9",
        corners=["ssgnp_0p475v_0c"], types=["delay"],
        lib_dir=str(tmp_path), output_dir=str(tmp_path / "out"),
        fmc_mode="parsed_scld", fmc_input_dir=str(tmp_path),
        vt_type="  svt ", rc_type="cworst",
    )
    assert cfg.vt_type == "svt"      # trimmed
    assert cfg.rc_type == "cworst"
    m = cfg.to_manifest_dict()
    assert m["vt_type"] == "svt" and m["rc_type"] == "cworst"


def test_config_defaults_empty(tmp_path):
    cfg = build_config(
        vendor="cdns", process="n2p", process_version="v0p9",
        corners=["c"], types=["delay"],
        lib_dir=str(tmp_path), output_dir=str(tmp_path / "out"),
        fmc_golden_dir=str(tmp_path),
    )
    assert cfg.vt_type == "" and cfg.rc_type == ""


class _Cfg:
    def __init__(self, vt="", rc=""):
        self.vt_type, self.rc_type = vt, rc


def test_vtrc_narrows_on_match():
    files = [Path("delay_ssgnp_svt_cworst.csv"), Path("delay_ssgnp_elvt_cbest.csv")]
    log = []
    out = _apply_vtrc(files, _Cfg(vt="svt", rc="cworst"), log, "ctx")
    assert out == [Path("delay_ssgnp_svt_cworst.csv")]
    assert not log


def test_vtrc_lenient_fallback_when_no_match():
    files = [Path("delay_ssgnp_a.csv"), Path("delay_ssgnp_b.csv")]
    log = []
    out = _apply_vtrc(files, _Cfg(vt="svt"), log, "ctx")
    assert out == files                     # filenames lack the token -> keep all
    assert any("svt" in line for line in log)


def test_vtrc_noop_when_unset():
    files = [Path("x.csv"), Path("y.csv")]
    log = []
    assert _apply_vtrc(files, _Cfg(), log, "ctx") == files
    assert not log
