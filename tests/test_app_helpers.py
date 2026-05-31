"""Display-free tests for the desktop app's pure helpers (no Tk window opened)."""

from cert_data_process.app import gui


def test_pr_class_thresholds():
    assert gui.pr_class(None) == "na"
    assert gui.pr_class(96) == "hi"
    assert gui.pr_class(95) == "hi"
    assert gui.pr_class(92) == "mid"
    assert gui.pr_class(89.9) == "lo"


def test_fmt_pr():
    assert gui.fmt_pr(None) == "—"
    assert gui.fmt_pr(93.25) == "93.2%" or gui.fmt_pr(93.25) == "93.3%"  # rounding
    assert gui.fmt_pr(100.0) == "100.0%"


def test_short_corner():
    assert gui.short_corner("ssgnp_0p450v_m40c") == "0p450v"


def test_corner_suggestions_dedup_sorted():
    index = [
        {"corners": ["ssgnp_0p465v_m40c", "ssgnp_0p450v_m40c"]},
        {"corners": ["ssgnp_0p450v_m40c"]},
        {},
    ]
    assert gui.corner_suggestions(index) == ["ssgnp_0p450v_m40c", "ssgnp_0p465v_m40c"]


def test_coverage_text():
    assert gui.coverage_text({"total": 1180, "covered": 1180}) == "1180/1180 (100%)"
    assert gui.coverage_text({"total": 0, "covered": 0}) == "0/0 (0%)"
    assert gui.coverage_text({"total": 1261, "covered": 1201}).startswith("1201/1261")


def test_importing_gui_opens_no_window():
    # Importing the module must not require a display or create a Tk root.
    assert hasattr(gui, "CertiApp")
