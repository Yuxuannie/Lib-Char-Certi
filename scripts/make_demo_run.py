#!/usr/bin/env python3
"""Generate the bundled demo run for the Lib-Char-Certi desktop console.

The demo lets a first-time user (internal or EDA vendor) launch the tool with no
real data and walk the whole outlier cross-check flow:

    python -m cert_data_process.app --demo

It writes ONE synthetic batch into ``cert_data_process/demo_run/`` containing
exactly the artifacts a real run leaves — the per-arc check CSVs and the PR
tables — then calls the production ``summary.build_batch`` + ``runs`` writers so
the run-record schema is guaranteed identical to a real run. The numbers are
fabricated but internally consistent: every PR figure is derived from the same
per-arc rows the Outliers/scatter/Common views read, so drilling in tells a
coherent story (no "100% over 0 arcs", no PR that disagrees with its arcs).

Re-run any time to regenerate; it overwrites the demo_run directory.
"""

from __future__ import annotations

import csv
import random
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from cert_data_process.web import runs, summary  # noqa: E402

DEMO_ROOT = REPO / "cert_data_process" / "demo_run"
# Fixed so the demo is reproducible (no wall-clock in the batch id).
WHEN_UTC = "2026-06-18T09:00:00+00:00"
TIMESTAMP = "20260618_090000"
NAME = "N2P v1.0 CDNS Best (DEMO)"
ABS_TOL_PS = 15.0  # Waiver_2 abs_tol for hold, applied to every corner.

CELLS = ["INVX1", "NAND2X1", "NOR2X1", "AOI22X1", "OAI21X2", "DFFX1",
         "MUX2X1", "XOR2X1", "BUFX4", "AND3X2"]
TRANS = ["rise", "fall"]

SIGMA_METRICS = ["Nominal", "Early_Sigma", "Late_Sigma"]
MOMENT_METRICS = ["Meanshift", "Std", "Skew"]

# (corner, type) -> {metric: (total, base_fail, w1_fail)} target shape.
# w1_fail <= base_fail; base_PR = (total-base_fail)/total, W1 recovers the rest.
PLAN = {
    ("ssgnp_0p675v_125c", "delay"): {
        "Nominal": (60, 0, 0), "Early_Sigma": (60, 2, 1), "Late_Sigma": (60, 6, 3),
        "Meanshift": (60, 1, 0), "Std": (60, 1, 1), "Skew": (60, 0, 0),
    },
    ("ssgnp_0p675v_125c", "slew"): {
        "Nominal": (40, 0, 0), "Early_Sigma": (40, 1, 0), "Late_Sigma": (40, 1, 1),
        "Meanshift": (40, 0, 0), "Std": (40, 0, 0), "Skew": (40, 0, 0),
    },
    ("ssgnp_0p675v_125c", "hold"): {
        # hold uses Late_Sigma only; base 88%, W1 ~91%, W2 (abs_tol) rescues more.
        "Late_Sigma": (50, 6, 4),
    },
    ("ssgnp_0p675v_m40c", "delay"): {
        "Nominal": (60, 0, 0), "Early_Sigma": (60, 0, 0), "Late_Sigma": (60, 2, 1),
        "Meanshift": (60, 0, 0), "Std": (60, 0, 0), "Skew": (60, 0, 0),
    },
    ("ssgnp_0p675v_m40c", "slew"): {
        "Nominal": (40, 0, 0), "Early_Sigma": (40, 0, 0), "Late_Sigma": (40, 3, 1),
        "Meanshift": (40, 0, 0), "Std": (40, 0, 0), "Skew": (40, 0, 0),
    },
    ("ssgnp_0p675v_m40c", "hold"): {
        "Late_Sigma": (50, 1, 1),
    },
}

CORNERS = ["ssgnp_0p675v_125c", "ssgnp_0p675v_m40c"]
TYPES = ["delay", "slew", "hold"]


def _arc_names(rng, n, row_type):
    """n distinct arc names like 'comb_NAND2X1_A_Z_rise_<i1>_<i2>'."""
    out = []
    for k in range(n):
        cell = CELLS[k % len(CELLS)]
        tr = TRANS[k % len(TRANS)]
        i1, i2 = rng.randint(0, 6), rng.randint(0, 6)
        out.append(f"comb_{cell}_A_Z_{tr}_{i1}_{i2}")
    return out


def _metric_cols(metric):
    return [f"{metric}_MC_value", f"{metric}_Lib_value", f"{metric}_Final_Status",
            f"{metric}_rel_err"]


def _gen_metric_values(rng, n, base_fail, w1_fail, *, hold=False):
    """Return per-arc dicts for one metric: mc, lib, status, rel, base/w1 pass.

    First `base_fail` arcs fail base; of those, `base_fail - w1_fail` are rescued by
    Waiver1 (CI +6%). For hold, the W1-survivors are placed within ABS_TOL so
    Waiver2 rescues them — making the W2 view visibly recover pass-rate."""
    rows = []
    for k in range(n):
        is_base_fail = k < base_fail
        # of the base fails, the LAST (base_fail - w1_fail) are W1-rescued
        rescued_by_w1 = is_base_fail and k >= w1_fail
        mc = round(rng.uniform(40.0, 120.0), 4)
        if not is_base_fail:
            lib = round(mc + rng.uniform(-0.4, 0.4), 4)          # tracks MC -> pass
        else:
            optimistic = (k % 2 == 0)                            # mix opt/pess
            if hold and rescued_by_w1:
                delta = rng.uniform(4.0, ABS_TOL_PS - 1.0)       # within abs_tol -> W2 rescue
            elif rescued_by_w1:
                delta = rng.uniform(2.0, 5.0)                    # small -> W1 rescue
            else:
                delta = rng.uniform(8.0, 22.0)                   # large -> stays failed
            lib = round(mc - delta if optimistic else mc + delta, 4)
        rel = round((lib - mc) / abs(mc), 6) if mc else 0.0
        base_pass = not is_base_fail
        w1_pass = base_pass or rescued_by_w1
        rows.append({
            "mc": mc, "lib": lib, "rel": rel,
            "final": "Pass" if base_pass else "Fail",
            "base": "Pass" if base_pass else "Fail",
            "w1": "Pass" if w1_pass else "Fail",
        })
    return rows


def _pr(total, fails):
    return round((total - fails) / total * 100, 1) if total else 0.0


def build():
    if DEMO_ROOT.exists():
        shutil.rmtree(DEMO_ROOT)
    batch_id = runs.make_batch_id(NAME, TIMESTAMP)
    out = runs.batch_dir(DEMO_ROOT, batch_id)
    (out / "combined" / "sigma").mkdir(parents=True, exist_ok=True)
    (out / "pr" / "sigma").mkdir(parents=True, exist_ok=True)
    (out / "pr" / "moments").mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(parents=True, exist_ok=True)

    sigma_pr_rows, moments_pr_rows = [], []

    for corner in CORNERS:
        for row_type in TYPES:
            plan = PLAN[(corner, row_type)]
            rng = random.Random(f"{corner}|{row_type}")  # deterministic per cell
            sig_metrics = ["Late_Sigma"] if row_type == "hold" else SIGMA_METRICS
            mom_metrics = [] if row_type == "hold" else MOMENT_METRICS
            n = max(plan[m][0] for m in plan)
            arcs = _arc_names(rng, n, row_type)

            # ---- per-arc sigma CSV ----
            sig_vals = {m: _gen_metric_values(rng, n, plan[m][1], plan[m][2],
                                              hold=(row_type == "hold" and m == "Late_Sigma"))
                        for m in sig_metrics}
            sig_header = ["Arc"]
            for m in sig_metrics:
                sig_header += _metric_cols(m) + [f"{m}_Base_Pass", f"{m}_Waiver1_CI_Enlarged"]
            sig_path = out / "combined" / "sigma" / f"{corner}_{row_type}_sigma_check_with_waivers.csv"
            with sig_path.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(sig_header)
                for i, arc in enumerate(arcs):
                    row = [arc]
                    for m in sig_metrics:
                        v = sig_vals[m][i]
                        row += [v["mc"], v["lib"], v["final"], v["rel"], v["base"], v["w1"]]
                    w.writerow(row)

            # ---- sigma PR table row ----
            def prs(metric):
                if metric not in plan:
                    return ("", "")
                t, bf, wf = plan[metric]
                return (_pr(t, bf), _pr(t, wf))
            nb, nw = prs("Nominal")
            eb, ew = prs("Early_Sigma")
            lb, lw = prs("Late_Sigma")
            total = n
            health = "OK"
            sigma_pr_rows.append([corner, row_type, nb, nw, eb, ew, lb, lw, total, total, health])

            # ---- per-arc moments CSV + moments PR row ----
            if mom_metrics:
                mom_vals = {m: _gen_metric_values(rng, n, plan[m][1], plan[m][2]) for m in mom_metrics}
                mom_header = ["Arc"]
                for m in mom_metrics:
                    mom_header += _metric_cols(m)
                mom_path = out / "combined" / "sigma" / f"{corner}_{row_type}_moments_check.csv"
                with mom_path.open("w", newline="", encoding="utf-8") as fh:
                    w = csv.writer(fh)
                    w.writerow(mom_header)
                    for i, arc in enumerate(arcs):
                        row = [arc]
                        for m in mom_metrics:
                            v = mom_vals[m][i]
                            row += [v["mc"], v["lib"], v["final"], v["rel"]]
                        w.writerow(row)
                mb, mw = prs("Meanshift")
                sb, sw = prs("Std")
                kb, kw = prs("Skew")
                moments_pr_rows.append([corner, row_type, mb, sb, kb, mw, sw, kw, total, total, health])

    # ---- write the two PR tables the run-record reader consumes ----
    with (out / "pr" / "sigma" / "sigma_PR_table_with_waivers.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Corner", "Type", "Nominal_Base_PR", "Nominal_PR_with_Waiver1",
                    "Early_Sigma_Base_PR", "Early_Sigma_PR_with_Waiver1",
                    "Late_Sigma_Base_PR", "Late_Sigma_PR_with_Waiver1",
                    "Total_Arcs", "Covered", "Data_Health"])
        w.writerows(sigma_pr_rows)
    with (out / "pr" / "moments" / "moments_PR_table.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Corner", "Type", "Meanshift_Base_PR", "Std_Base_PR", "Skew_Base_PR",
                    "Meanshift_PR_with_Waiver1", "Std_PR_with_Waiver1", "Skew_PR_with_Waiver1",
                    "Total_Arcs", "Covered", "Data_Health"])
        w.writerows(moments_pr_rows)

    # ---- build the run-record via the PRODUCTION builder (schema-identical) ----
    cfg = SimpleNamespace(
        output_dir=out, vendor="cdns", process="n2p", process_version="v1p0",
        corners=CORNERS, types=TYPES, vt_type="svt", rc_type="cworst",
        library_type="mb", recipe=out.name, lib_dir="/demo/lib (synthetic)",
        fmc_golden_dir="/demo/fmc (synthetic)", fmc_input_dir=None, fmc_mode="decks",
        lib_unit="ps", fmc_unit="ps",
        abs_tol_ps_by_corner={c: ABS_TOL_PS for c in CORNERS},
    )
    batch = summary.build_batch(cfg, stage_execution=[
        {"stage": s, "status": "passed", "pipeline": "sigma,moments", "reason": ""}
        for s in ("fmc_combine_data", "lib_join_sigma", "build_pr_table",
                  "get_pr_moments", "generate_pr_web_app")
    ], batch_id=batch_id, name=NAME, when_utc=WHEN_UTC)
    runs.write_run_record(DEMO_ROOT, batch_id, batch)
    runs.update_index(DEMO_ROOT, summary.build_index_summary(batch))

    (out / "logs" / "cert_data_process.log").write_text(
        "SYNTHETIC DEMO run — fabricated data for tutorial / first-launch use.\n"
        f"batch_id={batch_id}\n", encoding="utf-8")
    print(f"Demo run written: {out}")
    print(f"  status={batch['status']}  sigma_rows={len(batch['sigma'])}  moments_rows={len(batch['moments'])}")
    return batch_id


if __name__ == "__main__":
    build()
