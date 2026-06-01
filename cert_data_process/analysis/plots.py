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


def _coords(points, mode):
    """Return (xs, ys) arrays for the chosen plot mode.
    - lib_vs_mc:  x = MC value, y = Lib value
    - abs_vs_rel: x = SIGNED error Lib-MC (ps), y = signed rel error (%)
                  [optimistic Lib<MC < 0 on both axes]
    """
    if mode == "abs_vs_rel":
        xs = [(lib - mc) for mc, lib, *_ in points]
        ys = [((lib - mc) / abs(mc) * 100.0 if mc else 0.0) for mc, lib, *_ in points]
    else:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
    return xs, ys


def _needs_symlog(values, ratio: float = 100.0):
    """Decide if a (possibly signed) axis spans too wide a dynamic range for linear.

    Returns a linthresh (the half-width of the linear region around 0) when the
    max/min of nonzero magnitudes exceeds ``ratio``, else None. symlog (not log) is
    used because rel-error is signed (optimistic < 0) and may be exactly 0.
    """
    mags = sorted(abs(v) for v in values if v)
    if len(mags) < 3 or mags[0] <= 0:
        return None
    if mags[-1] / mags[0] <= ratio:
        return None
    return max(mags[0], 0.1)


def auto_log_recommended(points, mode="abs_vs_rel") -> bool:
    """True when the rel-error spread is wide enough that log (symlog) helps.
    The GUI uses this to set the Log-scale toggle's initial state; the user can
    still override. Only meaningful for the abs_vs_rel mode."""
    if mode != "abs_vs_rel":
        return False
    _xs, ys = _coords(points, mode)
    return _needs_symlog(ys) is not None


def build_scatter_figure(points, metric, mode="lib_vs_mc", highlight=None,
                         rel_threshold=None, optimistic_only=False, scale="auto", fig=None):
    """Build / refresh a professional outlier scatter Figure.

    Args:
        points: list of (mc, lib, is_outlier, arc) — from perarc.scatter_points().
        metric: metric name, e.g. 'Late_Sigma' (used for axis labels + units).
        mode: 'lib_vs_mc' or 'abs_vs_rel' (abs error vs rel error).
        highlight: set of arc strings to emphasize (larger, black-edged markers).
        rel_threshold: relative error threshold to draw a band/lines on the plot.
        optimistic_only: when True, keep only optimistic-risk points (Lib < MC).
        fig: reuse this Figure (cleared first) instead of creating one — lets the
             GUI keep one embedded canvas, so redraws are fast (no widget rebuild).
    Returns:
        matplotlib Figure (no pyplot state; safe for headless/Agg and Tk embedding).
    """
    highlight = highlight or set()
    if optimistic_only:
        points = [p for p in points if p[1] < p[0]]  # Lib < MC = optimistic risk
    if fig is None:
        fig = Figure(figsize=(6, 5), dpi=110)
    else:
        fig.clear()
    ax = fig.add_subplot(111)

    xs, ys = _coords(points, mode)

    # Reference geometry per mode.
    if mode == "abs_vs_rel":
        ax.axhline(0, color="#9ec5fe", lw=1.2, zorder=1)
        ax.axvline(0, color="#9ec5fe", lw=1.2, zorder=1)  # sign boundary: left = optimistic
        if rel_threshold:
            ax.axhline(rel_threshold * 100, color="#f97316", ls="--", lw=0.9, zorder=1)
            ax.axhline(-rel_threshold * 100, color="#f97316", ls="--", lw=0.9, zorder=1)
        ax.set_xlabel(f"Signed error Lib-MC ({metric_unit(metric) or 'ps'})  [optimistic < 0]", fontsize=10)
        ax.set_ylabel("Rel error (%)  [optimistic < 0]", fontsize=10)
        # Scale: "linear" forces linear, "symlog" forces symlog, "auto" uses symlog
        # only when the spread is wide (so small + huge outliers are both readable).
        if scale == "linear":
            use_log = False
        elif scale == "symlog":
            use_log = True
        else:
            use_log = _needs_symlog(ys) is not None
        if use_log:
            ax.set_yscale("symlog", linthresh=_needs_symlog(ys) or 0.1)
            ax.set_ylabel("Rel error (%, symlog)  [optimistic < 0]", fontsize=10)
            ltx = _needs_symlog(xs)
            if ltx:
                ax.set_xscale("symlog", linthresh=ltx)
    else:
        if xs and ys:
            lo = min(xs + ys)
            hi = max(xs + ys)
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

    # Vectorized: bucket points into a few categories and scatter each once.
    # (Per-point scatter calls were the cause of multi-minute redraws on big sets.)
    cats = {"pass": ([], []), "pess": ([], []), "opt": ([], []), "hi": ([], [])}
    n_opt = n_pess = 0
    for x, y, p in zip(xs, ys, points):
        mc, lib, is_out, arc = p
        if arc in highlight:
            key = "hi"
        elif not is_out:
            key = "pass"
        elif lib < mc:        # optimistic risk (lib claims better than MC)
            key = "opt"; n_opt += 1
        else:
            key = "pess"; n_pess += 1
        cats[key][0].append(x)
        cats[key][1].append(y)

    if cats["pass"][0]:
        ax.scatter(cats["pass"][0], cats["pass"][1], s=12, c="#cbd5e1",
                   edgecolors="none", alpha=0.5, zorder=2, label="pass")
    if cats["pess"][0]:
        ax.scatter(cats["pess"][0], cats["pess"][1], s=16, c="#f59e0b",
                   edgecolors="none", alpha=0.8, zorder=3, label="pessimistic")
    if cats["opt"][0]:
        ax.scatter(cats["opt"][0], cats["opt"][1], s=20, c="#dc2626",
                   edgecolors="none", alpha=0.85, zorder=4, label="optimistic (risk)")
    if cats["hi"][0]:
        ax.scatter(cats["hi"][0], cats["hi"][1], s=60, c="#1d4ed8",
                   edgecolors="black", linewidths=0.8, zorder=5, label="selected")

    ax.set_title(f"{metric}  (n={len(points)}, opt={n_opt}, pess={n_pess})", fontsize=10)
    ax.grid(True, color="#e5e7eb", lw=0.6, zorder=0)
    ax.tick_params(labelsize=8)
    ax.legend(loc="best", fontsize=7, framealpha=0.7)
    fig.tight_layout()
    return fig


def save_figure(fig, path, dpi: int = 200) -> None:
    """Save the figure to a PNG file at high resolution."""
    fig.savefig(str(path), dpi=dpi, bbox_inches="tight")
