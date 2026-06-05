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


def test_fmc_corner_matchers():
    from cert_data_process.app.gui import _fmc_corner_matchers
    assert _fmc_corner_matchers("ssgnp_0p475v_0c") == ["ssgnp_0p475v_0c", "0p475v"]
    assert _fmc_corner_matchers("") == []


def test_fmc_deck_for_arc_prefers_table_point(tmp_path):
    from cert_data_process.app.gui import _fmc_deck_for_arc
    p = tmp_path / "cons_svt_ssgnp_0p475v_0c.csv"
    p.write_text(
        "PVT,Cell,when,point,type,tool,deck\n"
        "ssgnp,INVD1,a,3;5,hold,fmc,/decks/INVD1_3_5/fastmontecarlo.log\n"
        "ssgnp,INVD1,b,2;2,hold,fmc,/decks/INVD1_2_2/fastmontecarlo.log\n"
        "ssgnp,OTHER,c,3;5,hold,fmc,/decks/OTHER.log\n"
    )
    # exact table-point (3,5) match wins over the first INVD1 row
    assert _fmc_deck_for_arc(p, "INVD1", "3", "5") == "/decks/INVD1_3_5/fastmontecarlo.log"
    # falls back to first cell row when point doesn't match
    assert _fmc_deck_for_arc(p, "INVD1", "9", "9") == "/decks/INVD1_3_5/fastmontecarlo.log"
    # no deck column / no cell -> None
    assert _fmc_deck_for_arc(p, "NOPE", "3", "5") is None
    assert _fmc_deck_for_arc(tmp_path / "missing.csv", "INVD1", "3", "5") is None
