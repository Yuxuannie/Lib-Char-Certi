from pathlib import Path

from scripts.compare_fmc_csv_byte_equal import run


def _write_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_run_all_equal(tmp_path):
    legacy_root = tmp_path / "legacy"
    new_root = tmp_path / "new"
    corners = ["ssgnp_0p450v_m40c", "ssgnp_0p465v_m40c"]
    types = ["delay", "hold"]

    for corner in corners:
        for type_name in types:
            file_name = f"fmc_result_n2p_v1p0_{corner}_{type_name}.csv"
            payload = f"header\r\n{corner},{type_name}\r\n".encode("utf-8")
            _write_file(legacy_root / corner / type_name / file_name, payload)
            _write_file(new_root / corner / type_name / file_name, payload)

    rc = run(
        legacy_root=legacy_root,
        new_root=new_root,
        process="n2p",
        process_version="v1p0",
        corners=corners,
        types=types,
    )
    assert rc == 0


def test_run_detects_diff_and_missing(tmp_path):
    legacy_root = tmp_path / "legacy"
    new_root = tmp_path / "new"

    # diff case
    name = "fmc_result_n2p_v1p0_ssgnp_0p450v_m40c_delay.csv"
    _write_file(legacy_root / "ssgnp_0p450v_m40c" / "delay" / name, b"A\r\n")
    _write_file(new_root / "ssgnp_0p450v_m40c" / "delay" / name, b"B\r\n")

    # missing file case (new side missing)
    missing_name = "fmc_result_n2p_v1p0_ssgnp_0p465v_m40c_hold.csv"
    _write_file(legacy_root / "ssgnp_0p465v_m40c" / "hold" / missing_name, b"C\r\n")

    rc = run(
        legacy_root=legacy_root,
        new_root=new_root,
        process="n2p",
        process_version="v1p0",
        corners=["ssgnp_0p450v_m40c", "ssgnp_0p465v_m40c"],
        types=["delay", "hold"],
    )
    assert rc == 1
