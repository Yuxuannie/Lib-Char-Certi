"""Waiver_2 (abs_tol) pass-rate recompute — pure, stdlib only.

Waiver_2 is a user-assigned absolute tolerance (ps) that applies to HOLD Late_Sigma
ONLY. A hold arc with |Lib - MC| <= abs_tol is waived. It STACKS on the existing
base + Waiver1 pass: an arc passes-with-W2 if it already passed base/W1, OR its
absolute error is within abs_tol.

This does NOT re-derive base/W1 — those per-arc verdicts are read straight from the
per-arc CSV the sigma engine already wrote (Late_Sigma_Base_Pass /
Late_Sigma_Waiver1_CI_Enlarged). W2 only adds the abs_tol relaxation on top, so the
single pass-rate engine stays the source of truth. The GUI waiver-level toggle and
waiver_3 reuse this function for interactive recompute (no subprocess per click).
"""

from __future__ import annotations

from typing import Optional


def _f(s) -> Optional[float]:
    try:
        return float(str(s).strip())
    except (ValueError, TypeError):
        return None


def _is_pass(v) -> bool:
    return str(v).strip().lower() in ("pass", "passed", "true")


def _is_covered(v) -> bool:
    # Uncovered arcs are written as "N/A" in Base_Pass; covered are Pass/Fail.
    return str(v).strip().lower() in ("pass", "fail", "passed", "failed")


def hold_abs_tol_pr(rows, abs_tol_ps: float, metric: str = "Late_Sigma") -> dict:
    """Recompute hold pass-rate with the abs_tol waiver stacked on base + Waiver1.

    Args:
        rows: per-arc dicts from the hold ``*_sigma_check_with_waivers.csv``.
        abs_tol_ps: absolute tolerance in ps (<=0 or None disables W2).
        metric: metric prefix (hold uses ``Late_Sigma``).
    Returns dict with covered, base_pass, w1_pass, w2_pass counts, the three PRs
    (base_pr / pr_w1 / pr_w2 over covered arcs), and n_waived_by_w2 (arcs newly
    rescued by abs_tol that base+W1 had failed).
    """
    tol = _f(abs_tol_ps) or 0.0
    mc_k, lib_k = f"{metric}_MC_value", f"{metric}_Lib_value"
    base_k, w1_k = f"{metric}_Base_Pass", f"{metric}_Waiver1_CI_Enlarged"

    covered = base_pass = w1_pass = w2_pass = n_waived_by_w2 = 0
    for r in rows:
        if not _is_covered(r.get(base_k, "")):
            continue
        covered += 1
        is_base = _is_pass(r.get(base_k, ""))
        is_w1 = is_base or _is_pass(r.get(w1_k, ""))
        mc, lib = _f(r.get(mc_k)), _f(r.get(lib_k))
        within_tol = tol > 0 and mc is not None and lib is not None and abs(lib - mc) <= tol
        is_w2 = is_w1 or within_tol
        base_pass += int(is_base)
        w1_pass += int(is_w1)
        w2_pass += int(is_w2)
        if within_tol and not is_w1:
            n_waived_by_w2 += 1

    pct = lambda n: round(n / covered * 100, 1) if covered else 0.0
    return {
        "covered": covered,
        "base_pass": base_pass,
        "w1_pass": w1_pass,
        "w2_pass": w2_pass,
        "base_pr": pct(base_pass),
        "pr_w1": pct(w1_pass),
        "pr_w2": pct(w2_pass),
        "n_waived_by_w2": n_waived_by_w2,
    }
