"""Professional outlier scatter: metric_unit, build_scatter_figure, save_figure."""

import matplotlib
matplotlib.use("Agg")

from cert_data_process.analysis.plots import metric_unit, build_scatter_figure, save_figure

PTS = [(40.0, 38.0, True, "combinational_A_Z_rise_A_rise_NO_CONDITION_3_5"),
       (30.0, 30.1, False, "combinational_B_Z_rise_A_rise_NO_CONDITION_3_6")]


def test_metric_unit():
    assert metric_unit("Late_Sigma") == "ps"
    assert metric_unit("Early_Sigma") == "ps"
    assert metric_unit("Meanshift") == "ps"
    assert metric_unit("Std") == "ps"
    assert metric_unit("Nominal") == "ps"
    assert metric_unit("Skew") == ""


def test_build_and_save(tmp_path):
    for mode in ("lib_vs_mc", "abs_vs_rel"):
        fig = build_scatter_figure(PTS, "Late_Sigma", mode=mode, rel_threshold=0.03)
        assert fig is not None
        p = tmp_path / f"{mode}.png"
        save_figure(fig, p, dpi=150)
        assert p.exists() and p.stat().st_size > 1000


def test_build_with_highlight():
    highlight = {"combinational_A_Z_rise_A_rise_NO_CONDITION_3_5"}
    fig = build_scatter_figure(PTS, "Late_Sigma", highlight=highlight)
    assert fig is not None


def test_optimistic_only_filters_to_lib_below_mc():
    # PTS[0] is optimistic (38<40); PTS[1] is pessimistic (30.1>30).
    fig = build_scatter_figure(PTS, "Late_Sigma", optimistic_only=True)
    assert fig is not None


def test_needs_symlog_detects_wide_spread():
    from cert_data_process.analysis.plots import _needs_symlog
    assert _needs_symlog([1.0, 2.0, 3.0]) is None          # narrow -> linear
    assert _needs_symlog([0.5, 5.0, 5000.0]) is not None    # 10000x spread -> symlog
    assert _needs_symlog([0.0, 0.0]) is None                # not enough data


def test_wide_spread_figure_builds(tmp_path):
    pts = [(100.0, 100.2, True, "combinational_A_..._3_5"),    # ~0.2% rel
           (100.0, 90.0, True, "combinational_B_..._3_6"),     # 10% rel
           (10.0, 200.0, True, "combinational_C_..._3_7")]     # 1900% rel -> wide
    fig = build_scatter_figure(pts, "Late_Sigma", mode="abs_vs_rel", rel_threshold=0.03)
    assert fig is not None
    p = tmp_path / "wide.png"
    save_figure(fig, p, dpi=120)
    assert p.exists() and p.stat().st_size > 1000


def test_auto_log_recommended():
    from cert_data_process.analysis.plots import auto_log_recommended
    narrow = [(100.0, 100.2, True, "a"), (100.0, 90.0, True, "b")]
    wide = [(100.0, 100.2, True, "a"), (100.0, 90.0, True, "b"), (10.0, 200.0, True, "c")]
    assert auto_log_recommended(narrow, "abs_vs_rel") is False
    assert auto_log_recommended(wide, "abs_vs_rel") is True
    assert auto_log_recommended(wide, "lib_vs_mc") is False   # only abs_vs_rel


def test_scale_param_forces_linear_or_log():
    wide = [(100.0, 100.2, True, "a"), (100.0, 90.0, True, "b"), (10.0, 200.0, True, "c")]
    # both should build without error; forcing linear must not raise on wide data
    assert build_scatter_figure(wide, "Late_Sigma", mode="abs_vs_rel", scale="linear") is not None
    assert build_scatter_figure(wide, "Late_Sigma", mode="abs_vs_rel", scale="symlog") is not None
    assert build_scatter_figure(wide, "Late_Sigma", mode="abs_vs_rel", scale="auto") is not None


def test_fig_reuse_clears_and_redraws():
    fig = build_scatter_figure(PTS, "Late_Sigma", mode="lib_vs_mc")
    again = build_scatter_figure(PTS, "Late_Sigma", mode="abs_vs_rel", fig=fig)
    assert again is fig                       # same Figure object reused
    assert len(fig.axes) == 1                 # cleared, not stacked
