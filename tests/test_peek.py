"""Pure file-region scanner behind the outlier 'Peek' (whole cell block / all rows)."""

from cert_data_process.app.gui import _scan_file_region

_LIB = """\
library (x) {
  cell (BUFD1) {
    pin (Z) { direction: output; }
  }
  cell (INVD1) {
    area : 1.0;
    pin (Z) {
      timing () { related_pin: "A"; }
    }
  }
  cell (NAND2) {
    area : 2.0;
  }
}
"""

_FMC = """\
PVT,Cell,when
ssgnp,INVD1,a
ssgnp,BUFD1,b
ssgnp,INVD1,c
ssgnp,NAND2,d
"""


def test_whole_cell_captures_full_brace_block(tmp_path):
    p = tmp_path / "x.lib"
    p.write_text(_LIB)
    window, ln = _scan_file_region(p, "cell (INVD1)", whole_cell=True)
    text = "\n".join(window)
    assert "cell (INVD1)" in text
    assert "timing ()" in text          # inside the block
    assert "cell (NAND2)" not in text    # stops at the block's closing brace
    # balanced: equal { and } in the captured block
    assert text.count("{") == text.count("}")
    assert ln == 5                       # INVD1 cell starts on line 5


def test_fmc_collects_all_matching_rows(tmp_path):
    p = tmp_path / "fmc.csv"
    p.write_text(_FMC)
    window, ln = _scan_file_region(p, "INVD1", whole_cell=False)
    assert len(window) == 2              # two INVD1 rows
    assert all("INVD1" in w for w in window)
    assert ln == 2


def test_max_lines_cap(tmp_path):
    p = tmp_path / "big.csv"
    p.write_text("INVD1\n" * 100)
    window, _ = _scan_file_region(p, "INVD1", whole_cell=False, max_lines=10)
    assert len(window) == 10
