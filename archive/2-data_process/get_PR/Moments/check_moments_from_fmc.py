#!/usr/bin/env python3
"""Moments pass-rate from FMC data only (no Full MC).

G4: moments (Meanshift / Std / Skew) Base_PR and PR_with_Waiver1 are computed
directly from the same FMC combine RPT used by the sigma flow
(`*_fmc_cdns_lib_comp.rpt`), which already carries MC_<param>, CDNS_Lib_<param>,
their CI bounds, and the per-row lib nominal. Moments apply to delay/slew only.

Reuses the unified pass logic from the sigma script so Base/Waiver1 semantics and
the relative-error thresholds (delay: Meanshift 1%, Std 2%, Skew 5%; slew:
Meanshift 2%, Std 4%, Skew 10%) stay in one place. Output mirrors the sigma PR
table: Base_PR + PR_with_Waiver1 + coverage/Data_Health (G1 + G2).
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import sys

import pandas as pd

# Reuse the proven, coverage-aware pass logic from the sigma script.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Sigma"))
from check_sigma_with_waivers import (  # noqa: E402
    check_pass_with_waivers,
    detect_vendor_columns,
    find_rpt_files,
)

MOMENT_PARAMS = ["Meanshift", "Std", "Skew"]


def parse_arguments():
    parser = argparse.ArgumentParser(description="Moments pass-rate from FMC data (Base_PR + PR_with_Waiver1)")
    parser.add_argument("--root_path", required=True, help="Directory containing the FMC *_fmc_cdns_lib_comp.rpt files")
    parser.add_argument("--corners", nargs="+", required=True)
    parser.add_argument("--types", nargs="+", required=True, help="delay and/or slew (moments do not apply to hold)")
    parser.add_argument("--log_level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    return parser.parse_args()


def process_moments_file(file_path, type_name):
    """Compute moments Base_PR + Waiver1 (coverage-aware) for one FMC RPT."""

    if type_name not in ("delay", "slew"):
        logging.info(f"Skipping {type_name} for moments (moments apply to delay/slew only)")
        return None

    logging.info("=" * 80)
    logging.info(f"Processing moments from FMC RPT: {file_path} (type={type_name})")
    try:
        df = pd.read_csv(file_path)
    except Exception:
        logging.error(f"Failed to read {file_path}", exc_info=True)
        return None

    vendor_prefix = detect_vendor_columns(df)
    logging.info(f"Vendor prefix: {vendor_prefix} | shape: {df.shape}")

    result_df = pd.DataFrame()
    result_df["Arc"] = df["Arc"]
    moments_summary = {}

    for param in MOMENT_PARAMS:
        required = [f"MC_{param}", f"{vendor_prefix}_{param}", f"MC_{param}_LB", f"MC_{param}_UB"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            logging.warning(f"  {param}: missing columns {missing}; skipping this moment")
            continue

        base_list, w1_list, status_list, mc_list, lib_list = [], [], [], [], []
        covered = base_pass = pass_w1 = uncovered = 0
        uncovered_arcs = []

        for _, row in df.iterrows():
            r = check_pass_with_waivers(row, type_name, param, lib_prefix=vendor_prefix)
            mc_list.append(r["mc_value"])
            lib_list.append(r["lib_value"])
            if not r.get("covered", True):
                base_list.append("N/A")
                w1_list.append("N/A")
                status_list.append("No_Lib")
                uncovered += 1
                uncovered_arcs.append(row["Arc"])
                continue
            covered += 1
            bp = r["base_pass"]
            w1 = bp or r["waiver1_ci_enlarged"]
            base_pass += 1 if bp else 0
            pass_w1 += 1 if w1 else 0
            base_list.append("Pass" if bp else "Fail")
            w1_list.append("Pass" if w1 else "Fail")
            status_list.append(r["final_status"])

        result_df[f"{param}_MC_value"] = mc_list
        result_df[f"{param}_Lib_value"] = lib_list
        result_df[f"{param}_Base_Pass"] = base_list
        result_df[f"{param}_PR_with_Waiver1"] = w1_list
        result_df[f"{param}_Final_Status"] = status_list

        total_golden = covered + uncovered
        base_pr = (base_pass / covered * 100) if covered else 0.0
        pr_w1 = (pass_w1 / covered * 100) if covered else 0.0
        moments_summary[param] = {
            "base_pr": base_pr,
            "pr_with_waiver1": pr_w1,
            "total_arcs": covered,
            "uncovered": uncovered,
            "total_golden": total_golden,
        }

        coverage_pct = (covered / total_golden * 100) if total_golden else 0.0
        logging.info(f"  {param}: golden={total_golden} covered={covered} ({coverage_pct:.1f}%) uncovered={uncovered}")
        if covered == 0:
            logging.error(f"    DATA_HEALTH=NO_DATA: lib covers 0/{total_golden} {param} arcs; PR not meaningful.")
        elif coverage_pct < 90.0:
            logging.warning(f"    DATA_HEALTH=LOW_COVERAGE: {covered}/{total_golden} ({coverage_pct:.1f}%) covered; examples {uncovered_arcs[:5]}")
        if covered:
            logging.info(f"    Base PR: {base_pr:.1f}% | PR with Waiver1: {pr_w1:.1f}%")

    if not moments_summary:
        logging.warning(f"No moment parameters computed for {file_path}")
        return None

    if hasattr(process_moments_file, "summaries"):
        process_moments_file.summaries[(os.path.basename(file_path), type_name)] = moments_summary
    else:
        process_moments_file.summaries = {(os.path.basename(file_path), type_name): moments_summary}

    out = file_path.replace(".rpt", "_moments_check.csv")
    result_df.to_csv(out, index=False)
    logging.info(f"Moments per-arc output: {out}")
    return out


def _corner_from_name(file_name, corners=None):
    # Prefer matching one of the requested corners as a substring (robust for
    # arbitrary corner naming incl. SCLD like ssgnp_0p475v_0c_cworst_CCworst);
    # fall back to the legacy regex.
    if corners:
        hits = [c for c in corners if c and c in file_name]
        if hits:
            return max(hits, key=len)
    import re
    m = re.search(r"(ssg[ng][pg]_[0-9]p[0-9]+v_[mn][0-9]+c)", file_name)
    return m.group(1) if m else file_name


def generate_moments_summary_table(results, root_path, corners=None):
    cov_cols = ["Total_Arcs", "Covered", "Uncovered", "Coverage", "Data_Health"]
    pr_cols = []
    for p in MOMENT_PARAMS:
        pr_cols += [f"{p}_Base_PR", f"{p}_PR_with_Waiver1"]

    rows = []
    corner_list = sorted({_corner_from_name(fn, corners) for (fn, _t) in results})
    types = sorted({t for (_fn, t) in results})
    for corner in corner_list:
        for type_name in types:
            key = next((k for k in results if _corner_from_name(k[0], corners) == corner and k[1] == type_name), None)
            row = {"Corner": corner, "Type": type_name}
            if key is None:
                for c in pr_cols:
                    row[c] = "N/A"
                row.update({"Total_Arcs": 0, "Covered": 0, "Uncovered": 0, "Coverage": "0.0%", "Data_Health": "NO_DATA"})
                rows.append(row)
                continue
            rates = results[key]
            cov_set = False
            for p in MOMENT_PARAMS:
                if p in rates:
                    row[f"{p}_Base_PR"] = f"{rates[p]['base_pr']:.1f}%"
                    row[f"{p}_PR_with_Waiver1"] = f"{rates[p]['pr_with_waiver1']:.1f}%"
                    if not cov_set:
                        total = rates[p]["total_golden"]
                        covered = rates[p]["total_arcs"]
                        unc = rates[p]["uncovered"]
                        if covered == 0:
                            health = "NO_DATA"
                        elif total > 0 and covered / total < 0.9:
                            health = "LOW_COVERAGE"
                        else:
                            health = "OK"
                        row.update({
                            "Total_Arcs": total, "Covered": covered, "Uncovered": unc,
                            "Coverage": f"{(covered/total*100):.1f}%" if total else "0.0%",
                            "Data_Health": health,
                        })
                        cov_set = True
                else:
                    row[f"{p}_Base_PR"] = "N/A"
                    row[f"{p}_PR_with_Waiver1"] = "N/A"
            if not cov_set:
                row.update({"Total_Arcs": 0, "Covered": 0, "Uncovered": 0, "Coverage": "0.0%", "Data_Health": "NO_DATA"})
            rows.append(row)

    df = pd.DataFrame(rows, columns=["Corner", "Type"] + pr_cols + cov_cols)
    csv_file = os.path.join(root_path, "moments_PR_table.csv")
    df.to_csv(csv_file, index=False)

    summary = "Moments Pass-Rate Summary (from FMC data; Base_PR + PR_with_Waiver1)\n\n"
    summary += "Params: Meanshift, Std, Skew (delay/slew only). PR over COVERED arcs only.\n"
    summary += "Data_Health: OK | LOW_COVERAGE (<90%) | NO_DATA (0 covered).\n\n"
    summary += df.to_string(index=False) if not df.empty else "No moments data"
    summary_file = os.path.join(root_path, "moments_summary_table.txt")
    with open(summary_file, "w") as f:
        f.write(summary)
    logging.info(f"Moments PR table: {csv_file}")
    logging.info(f"Moments summary: {summary_file}")
    return summary_file, csv_file


def main():
    args = parse_arguments()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(f"moments_check_{timestamp}.log"), logging.StreamHandler()],
    )
    logging.info("=" * 80)
    logging.info("Moments pass-rate from FMC data (Full MC removed)")
    logging.info("Base_PR = relative-error OR CI-bounds; Waiver1 = CI +6%; over COVERED arcs only")
    logging.info("=" * 80)

    moments_types = [t for t in args.types if t in ("delay", "slew")]
    if not moments_types:
        logging.warning("No delay/slew types requested; moments produce nothing.")
        return

    rpt_files = find_rpt_files(args.root_path, args.corners, moments_types)
    if not rpt_files:
        logging.error("No FMC RPT files found for moments.")
        return

    results = {}
    for (corner, type_name), file_path in rpt_files.items():
        if process_moments_file(file_path, type_name):
            key = (os.path.basename(file_path), type_name)
            results[key] = process_moments_file.summaries[key]

    if results:
        summary_file, csv_file = generate_moments_summary_table(results, args.root_path, corners=args.corners)
        with open(summary_file) as f:
            print("\n" + "=" * 50 + "\nMOMENTS PASS-RATE SUMMARY:\n" + "=" * 50)
            print(f.read())
            print("=" * 50)
    else:
        logging.warning("No moments results produced.")


if __name__ == "__main__":
    main()
