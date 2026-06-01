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


def test_fig_reuse_clears_and_redraws():
    fig = build_scatter_figure(PTS, "Late_Sigma", mode="lib_vs_mc")
    again = build_scatter_figure(PTS, "Late_Sigma", mode="abs_vs_rel", fig=fig)
    assert again is fig                       # same Figure object reused
    assert len(fig.axes) == 1                 # cleared, not stacked
