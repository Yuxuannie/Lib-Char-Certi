"""Professional outlier scatter via matplotlib (no pyplot -> headless-safe + Tk-embeddable).

Build a Figure with build_scatter_figure(); the GUI wraps it in FigureCanvasTkAgg,
tests render it via the Agg backend and save_figure(). Axis labels carry units so
the plot is immediately readable without context.
"""

from __future__ import annotations

from matplotlib.figure import Figure

_PS = {"Nominal", "Early_Sigma", "Late_Sigma", "Std", "Meanshift"}


def metric_unit(metric: str) -> str:
    """Return the physical unit string for a metric ('ps' or '' for dimensionless)."""
    return "ps" if metric in _PS else ""


def _ulabel(metric: str) -> str:
    u = metric_unit(metric)
    return f"{metric} ({u})" if u else metric


def build_scatter_figure(points, metric, mode="lib_vs_mc", highlight=None, rel_threshold=None):
    """Build a professional outlier scatter Figure.

    Args:
        points: list of (mc, lib, is_outlier, arc) — from perarc.scatter_points().
        metric: metric name, e.g. 'Late_Sigma' (used for axis labels + units).
        mode: 'lib_vs_mc' (Lib value vs MC value) or 'residual' (rel error vs MC).
        highlight: set of arc strings to emphasize (larger, outlined markers).
        rel_threshold: relative error threshold to draw a band/lines on the plot.
    Returns:
        matplotlib Figure (no pyplot state; safe for headless/Agg and Tk embedding).
    """
    highlight = highlight or set()
    fig = Figure(figsize=(6, 5), dpi=120)
    ax = fig.add_subplot(111)

    mcs = [p[0] for p in points]
    libs = [p[1] for p in points]

    if mode == "residual":
        xs = mcs
        ys = [((lib - mc) / abs(mc) * 100.0 if mc else 0.0) for mc, lib in zip(mcs, libs)]
        ax.axhline(0, color="#9ec5fe", lw=1.2, zorder=1)
        if rel_threshold:
            ax.axhline(rel_threshold * 100, color="#f97316", ls="--", lw=0.9, zorder=1)
            ax.axhline(-rel_threshold * 100, color="#f97316", ls="--", lw=0.9, zorder=1)
        ax.set_xlabel(f"MC {_ulabel(metric)}", fontsize=10)
        ax.set_ylabel("Rel error (%)", fontsize=10)
    else:
        xs, ys = mcs, libs
        if mcs and libs:
            lo = min(mcs + libs)
            hi = max(mcs + libs)
            if hi > lo:
                ax.plot([lo, hi], [lo, hi], color="#9ec5fe", ls="--", lw=1.2, zorder=1)
                if rel_threshold:
                    ax.fill_between(
                        [lo, hi],
                        [lo * (1 - rel_threshold), hi * (1 - rel_threshold)],
                        [lo * (1 + rel_threshold), hi * (1 + rel_threshold)],
                        color="#9ec5fe", alpha=0.12, zorder=0,
                    )
        ax.set_xlabel(f"MC {_ulabel(metric)}", fontsize=10)
        ax.set_ylabel(f"Lib {_ulabel(metric)}", fontsize=10)

    for x, y, p in zip(xs, ys, points):
        is_out, arc = p[2], p[3]
        big = arc in highlight
        ax.scatter(
            [x], [y],
            s=50 if big else 14,
            c="#dc2626" if is_out else "#94a3b8",
            edgecolors="black" if big else "none",
            linewidths=0.8,
            zorder=3 if big else 2,
            alpha=0.85 if is_out else 0.55,
        )

    n_out = sum(1 for p in points if p[2])
    ax.set_title(f"{metric}  (n={len(points)}, outliers={n_out}, red = outlier)", fontsize=10)
    ax.grid(True, color="#e5e7eb", lw=0.6, zorder=0)
    ax.tick_params(labelsize=8)
    fig.tight_layout()
    return fig


def save_figure(fig, path, dpi: int = 200) -> None:
    """Save the figure to a PNG file at high resolution."""
    fig.savefig(str(path), dpi=dpi, bbox_inches="tight")
