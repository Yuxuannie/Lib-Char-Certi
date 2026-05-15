#!/usr/bin/env python3
 
import os
import pandas as pd
import numpy as np
import sys
import logging
import datetime
import argparse
from pathlib import Path
 
"""
Enhanced Sigma Pass Rate Calculation Script
 
This script processes sigma RPT files (from enhanced Combine_FMC_and_CDNS.py) and
calculates pass rates using LVF Sigma Checking Criteria with CI enlargement.
Supports both CDNS (Cadence) and SNPS (Synopsys) automatically.
 
Four-Tier Checking System:
1. Relative error <= threshold -> Pass
2. Value within original CI bounds -> Pass 
3. Value within CI + 6% enlargement -> Waived (treated as Pass)
4. Absolute error <= slew-dependent threshold -> Pass
 
Criteria per slides:
- Delay: rel_tol <= Â±3%, abs_tol <= Â±max(0.005Ã—slew, 1ps)
- Slew: rel_tol <= Â±6%, abs_tol <= Â±max(0.01Ã—slew, 2ps)
- Hold: rel_tol <= Â±3%, abs_tol <= Â±max(0.005Ã—slew, 10ps)
 
Final Version Features:
- Generates exactly 2 PNG files: Early_Sigma and Late_Sigma tier analysis
- 1-digit precision for pass rates
- Fixed layout issues (larger legends, no title overlap)
- Type â†’ Corner organization with visual separators
 
Output: sigma_PR_table.csv for moments integration
"""
 
def parse_arguments():
    """
    Parse command line arguments
    """
    parser = argparse.ArgumentParser(description='Enhanced Sigma Pass Rate Calculation Script')
    parser.add_argument('--root_path',
                       help='Root directory path containing sigma RPT files',
                       required=True)
    parser.add_argument('--corners',
                       nargs='+',
                       help='List of corner names',
                       required=True)
    parser.add_argument('--types',
                       nargs='+',
                       help='List of types (delay, slew, hold)',
                       required=True)
    parser.add_argument('--log_level',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default='INFO',
                       help='Logging level')
 
    return parser.parse_args()
 
def setup_logging(input_file):
    """
    Set up logging configuration to log to both console and file
 
    Args:
        input_file: The input file path to derive the log file name
 
    Returns:
        str: Path to the log file
    """
    # Create a log file name based on the input file
    input_name = os.path.basename(input_file)
    log_file = os.path.join(os.path.dirname(input_file), f"{input_name}.log")
 
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
 
    logging.info(f"Log file created at: {log_file}")
    return log_file
 
def detect_vendor_columns(df):
    """
    Auto-detect whether this is CDNS or SNPS data based on column names
    Returns the appropriate column prefix
    """
    columns = df.columns.tolist()
 
    # Check for CDNS columns (case insensitive)
    cdns_patterns = ['cdns_lib', 'CDNS_Lib', 'Cdns_Lib']
    snps_patterns = ['snps_lib', 'SNPS_Lib', 'Snps_Lib']
 
    for col in columns:
        for pattern in cdns_patterns:
            if pattern in col:
                logging.info(f"Detected CDNS vendor from column: {col}")
                return 'CDNS_Lib'
        for pattern in snps_patterns:
            if pattern in col:
                logging.info(f"Detected SNPS vendor from column: {col}")
                return 'SNPS_Lib'
 
    # If no exact match, try partial matching
    for col in columns:
        if 'cdns' in col.lower():
            logging.info(f"Detected CDNS vendor (partial match) from column: {col}")
            return 'CDNS_Lib'
        elif 'snps' in col.lower():
            logging.info(f"Detected SNPS vendor (partial match) from column: {col}")
            return 'SNPS_Lib'
 
    # Default to CDNS if nothing found
    logging.warning("Could not detect vendor, defaulting to CDNS_Lib")
    return 'CDNS_Lib'
 
def check_pass_with_waivers(row, type_name, param_name, mc_prefix='MC', lib_prefix=None):
    """
    Unified pass checking function with structured waivers for both sigma and moments

    Base Pass Criteria:
    - Check 1: Error-Based Pass (rel_pass OR abs_pass)
    - Check 2: CI Bounds Pass (lib value within MC CI bounds)
    - Base Pass = Check 1 OR Check 2

    Waivers:
    - Waiver 1: CI Enlargement (CI ± 6%)
    - Waiver 2: Optimistic Error Only (lib < mc)

    Args:
        row: DataFrame row with data
        type_name: 'delay', 'slew', or 'hold'
        param_name: Parameter name (e.g., 'Early_Sigma', 'Std', 'Meanshift')
        mc_prefix: Prefix for MC columns (default: 'MC')
        lib_prefix: Prefix for lib columns (auto-detect if None)

    Returns:
        dict: {
            'base_pass': bool,
            'pass_reason': str,  # rel_pass|abs_pass|ci_bounds|fail
            'waiver1_ci_enlarged': bool,
            'error_direction': 'optimistic'|'pessimistic',
            'final_status': 'Pass'|'Waived_CI'|'Fail',
            'abs_err': float,
            'rel_err': float,
            'mc_value': float,
            'lib_value': float,
            'mc_ci_lb': float,
            'mc_ci_ub': float
        }
    """
    arc_name = row['Arc']
    logging.debug(f"Checking {param_name} for Arc: {arc_name}")

    # Extract necessary values
    rel_pin_slew = row['rel_pin_slew']

    # Auto-detect lib prefix if not provided (for sigma files)
    if lib_prefix is None:
        lib_prefix = detect_vendor_columns(pd.DataFrame([row]))

    try:
        # Get MC and Lib values
        mc_value = row[f"{mc_prefix}_{param_name}"]
        lib_value = row[f"{lib_prefix}_{param_name}"]

        # Get CI bounds
        mc_ci_lb = row[f"{mc_prefix}_{param_name}_LB"]
        mc_ci_ub = row[f"{mc_prefix}_{param_name}_UB"]

        # Get or calculate errors
        if f"{lib_prefix}_{param_name}_Dif" in row:
            abs_err = row[f"{lib_prefix}_{param_name}_Dif"]  # Pre-calculated
        else:
            abs_err = lib_value - mc_value  # Calculate

        if f"{lib_prefix}_{param_name}_Rel" in row:
            rel_err = row[f"{lib_prefix}_{param_name}_Rel"]  # Pre-calculated
        else:
            rel_err = (lib_value - mc_value) / abs(mc_value) if mc_value != 0 else 0  # Calculate

        logging.debug(f"  rel_pin_slew: {rel_pin_slew}")
        logging.debug(f"  {mc_prefix}_{param_name}: {mc_value}")
        logging.debug(f"  {lib_prefix}_{param_name}: {lib_value}")
        logging.debug(f"  MC CI: [{mc_ci_lb}, {mc_ci_ub}]")
        logging.debug(f"  abs_err: {abs_err}, rel_err: {rel_err}")

    except KeyError as e:
        logging.error(f"Missing column for {param_name}: {e}")
        return {
            'base_pass': False, 'pass_reason': 'missing_data', 'waiver1_ci_enlarged': False,
            'error_direction': 'unknown', 'final_status': 'Fail',
            'abs_err': None, 'rel_err': None, 'mc_value': None, 'lib_value': None,
            'mc_ci_lb': None, 'mc_ci_ub': None
        }

    # Set thresholds based on type and parameter
    if type_name == 'delay':
        if param_name in ['Early_Sigma', 'Late_Sigma']:
            rel_threshold = 0.03  # 3% for sigma
            ps_value = 1
            slew_multiplier = 0.005
        elif param_name == 'Meanshift':
            rel_threshold = 0.01  # 1% for moments meanshift
            ps_value = 1
            slew_multiplier = 0.005
        elif param_name == 'Std':
            rel_threshold = 0.02  # 2% for moments std
            ps_value = 1
            slew_multiplier = 0.005
        else:  # Skew
            rel_threshold = 0.05  # 5% for moments skew
            ps_value = 1
            slew_multiplier = 0.005
    elif type_name == 'slew':
        if param_name in ['Early_Sigma', 'Late_Sigma']:
            rel_threshold = 0.06  # 6% for sigma
            ps_value = 2
            slew_multiplier = 0.01
        elif param_name == 'Meanshift':
            rel_threshold = 0.02  # 2% for moments meanshift
            ps_value = 1  # 1ps for slew in moments script
            slew_multiplier = 0.005
        elif param_name == 'Std':
            rel_threshold = 0.04  # 4% for moments std
            ps_value = 1
            slew_multiplier = 0.005
        else:  # Skew
            rel_threshold = 0.10  # 10% for moments skew
            ps_value = 1
            slew_multiplier = 0.005
    else:  # hold
        rel_threshold = 0.03  # 3% for hold
        ps_value = 10
        slew_multiplier = 0.005

    # **CHECK 1: Error-Based Pass (rel OR abs)**
    rel_pass = abs(rel_err) <= rel_threshold
    abs_threshold = max(slew_multiplier * rel_pin_slew, ps_value * 1e-12)
    abs_pass = abs(abs_err) <= abs_threshold

    error_based_pass = rel_pass or abs_pass

    # **CHECK 2: CI Bounds Pass**
    ci_lb = min(mc_ci_lb, mc_ci_ub)
    ci_ub = max(mc_ci_lb, mc_ci_ub)
    ci_bounds_pass = (ci_lb <= lib_value <= ci_ub)

    # **BASE PASS = Check 1 OR Check 2**
    base_pass = error_based_pass or ci_bounds_pass

    # Determine pass reason
    if base_pass:
        if rel_pass and abs_pass:
            pass_reason = "both"
        elif rel_pass:
            pass_reason = "rel_pass"
        elif abs_pass:
            pass_reason = "abs_pass"
        elif ci_bounds_pass:
            pass_reason = "ci_bounds"
        else:
            pass_reason = "unknown"
    else:
        pass_reason = "fail"

    # **WAIVER 1: CI Enlargement (6%)**
    ci_width = abs(ci_ub - ci_lb)
    ci_enlargement_amount = ci_width * 0.06  # 6% enlargement
    enlarged_lb = ci_lb - ci_enlargement_amount
    enlarged_ub = ci_ub + ci_enlargement_amount
    waiver1_ci_enlarged = (enlarged_lb <= lib_value <= enlarged_ub)

    # **WAIVER 2: Determine Error Direction**
    error_direction = 'optimistic' if lib_value < mc_value else 'pessimistic'

    # **FINAL STATUS**
    if base_pass:
        final_status = "Pass"
    elif waiver1_ci_enlarged:
        final_status = "Waived_CI"
    else:
        final_status = "Fail"

    logging.debug(f"  Results for {param_name}: base_pass={base_pass}, waiver1={waiver1_ci_enlarged}, error_dir={error_direction}, final={final_status}")

    return {
        'base_pass': base_pass,
        'pass_reason': pass_reason,
        'waiver1_ci_enlarged': waiver1_ci_enlarged,
        'error_direction': error_direction,
        'final_status': final_status,
        'abs_err': abs_err,
        'rel_err': rel_err,
        'mc_value': mc_value,
        'lib_value': lib_value,
        'mc_ci_lb': mc_ci_lb,
        'mc_ci_ub': mc_ci_ub
    }

def check_sigma_pass_fail_with_tiers(row, type_name, sigma_type, vendor_prefix):
    """
    Check sigma parameter using four-tier system with detailed tier tracking
 
    Args:
        row: DataFrame row with sigma data
        type_name: 'delay', 'slew', or 'hold'
        sigma_type: 'Early_Sigma' or 'Late_Sigma'
        vendor_prefix: 'CDNS_Lib' or 'SNPS_Lib'
 
    Returns:
        dict: Detailed results for each tier
    """
    arc_name = row['Arc']
    logging.debug(f"Checking {sigma_type} for Arc: {arc_name}")
 
    # Extract the necessary values
    rel_pin_slew = row['rel_pin_slew']
 
    # Extract FMC and Lib values with error handling
    try:
        fmc_value = row[f"MC_{sigma_type}"]              # FMC golden (sim_sigma)
        lib_value = row[f"{vendor_prefix}_{sigma_type}"] # Library value (lib_sigma)
        fmc_lb = row[f"MC_{sigma_type}_LB"]              # FMC lower bound
        fmc_ub = row[f"MC_{sigma_type}_UB"]              # FMC upper bound
        abs_err = row[f"{vendor_prefix}_{sigma_type}_Dif"]      # lib_sigma - sim_sigma
        rel_err = row[f"{vendor_prefix}_{sigma_type}_Rel"]      # Pre-calculated relative error
 
        # Get nominal value for denominator calculation (if available)
        lib_nominal = row.get(f'{vendor_prefix}_Nominal', None)
 
        logging.debug(f"  rel_pin_slew: {rel_pin_slew}")
        logging.debug(f"  MC_{sigma_type}: {fmc_value}")
        logging.debug(f"  {vendor_prefix}_{sigma_type}: {lib_value}")
        logging.debug(f"  MC_{sigma_type}_LB: {fmc_lb}")
        logging.debug(f"  MC_{sigma_type}_UB: {fmc_ub}")
 
    except KeyError as e:
        logging.error(f"Missing column: {e}")
        return {
            'tier1_pass': False, 'tier2_pass': False, 'tier3_pass': False, 'tier4_pass': False,
            'overall_pass': False, 'pass_reason': 'missing_data'
        }
 
    # Set thresholds based on type
    if type_name == 'delay':
        sigma_rel_threshold = 0.03      # 3% for delay
        ps_value = 1                    # 1ps for delay
        slew_multiplier = 0.005         # 0.005*slew for delay
    elif type_name == 'slew':
        sigma_rel_threshold = 0.06      # 6% for slew
        ps_value = 2                    # 2ps for slew
        slew_multiplier = 0.01          # 0.01*slew for slew
    else:  # hold/constraint
        sigma_rel_threshold = 0.03      # 3% for constraint
        ps_value = 10                   # 10ps for constraint
        slew_multiplier = 0.005         # 0.005*slew for constraint
 
    # CI enlargement factor (6% as per slides)
    ci_enlargement = 0.06
 
    # Calculate proper relative error using max denominator
    if lib_nominal is not None:
        max_denom = max(abs(lib_nominal), abs(fmc_value))
        sigma_rel_err = (lib_value - fmc_value) / max_denom
    else:
        sigma_rel_err = (lib_value - fmc_value) / abs(fmc_value)
 
    # Initialize tier results
    tier_results = {
        'tier1_pass': False,  # Relative threshold
        'tier2_pass': False,  # CI bounds
        'tier3_pass': False,  # CI enlarged
        'tier4_pass': False,  # Absolute threshold
        'overall_pass': False,
        'pass_reason': 'fail'
    }
 
    # **TIER 1: Relative error within threshold**
    tier1_pass = abs(sigma_rel_err) <= sigma_rel_threshold
    tier_results['tier1_pass'] = tier1_pass
    logging.debug(f"  Tier 1 - Relative error: |{sigma_rel_err}| <= {sigma_rel_threshold} -> {tier1_pass}")
 
    if tier1_pass:
        tier_results['overall_pass'] = True
        tier_results['pass_reason'] = 'tier1_rel'
        return tier_results
 
    # **TIER 2: Value within original CI bounds**
    ci_lb = min(fmc_lb, fmc_ub)
    ci_ub = max(fmc_lb, fmc_ub)
    tier2_pass = (ci_lb <= lib_value <= ci_ub)
    tier_results['tier2_pass'] = tier2_pass
    logging.debug(f"  Tier 2 - CI bounds: {ci_lb} <= {lib_value} <= {ci_ub} -> {tier2_pass}")
 
    if tier2_pass:
        tier_results['overall_pass'] = True
        tier_results['pass_reason'] = 'tier2_ci'
        return tier_results
 
    # **TIER 3: Value within CI + enlargement**
    ci_width = abs(ci_ub - ci_lb)
    ci_enlargement_amount = ci_width * ci_enlargement
    enlarged_lb = ci_lb - ci_enlargement_amount
    enlarged_ub = ci_ub + ci_enlargement_amount
    tier3_pass = (enlarged_lb <= lib_value <= enlarged_ub)
    tier_results['tier3_pass'] = tier3_pass
    logging.debug(f"  Tier 3 - CI enlarged: {enlarged_lb} <= {lib_value} <= {enlarged_ub} -> {tier3_pass}")
 
    if tier3_pass:
        tier_results['overall_pass'] = True
        tier_results['pass_reason'] = 'tier3_waived'
        return tier_results
 
    # **TIER 4: Absolute error check**
    abs_threshold = max(slew_multiplier * rel_pin_slew, ps_value * 1e-12)
    tier4_pass = abs(abs_err) <= abs_threshold
    tier_results['tier4_pass'] = tier4_pass
    logging.debug(f"  Tier 4 - Absolute error: |{abs_err}| <= {abs_threshold} -> {tier4_pass}")
 
    if tier4_pass:
        tier_results['overall_pass'] = True
        tier_results['pass_reason'] = 'tier4_abs'
        return tier_results
 
    # **FAILED all tiers**
    tier_results['pass_reason'] = 'fail_all_tiers'
    return tier_results
 
def debug_available_files(root_path):
    """
    Debug helper to show what files are actually available
    """
    try:
        all_files = os.listdir(root_path)
        rpt_files = [f for f in all_files if f.endswith('.rpt')]
        fmc_files = [f for f in all_files if 'fmc' in f.lower()]
 
        logging.info(f"Debug - Total files in directory: {len(all_files)}")
        logging.info(f"Debug - Total .rpt files: {len(rpt_files)}")
        logging.info(f"Debug - Total files containing 'fmc': {len(fmc_files)}")
 
        if fmc_files:
            logging.info("Debug - Sample FMC files:")
            for i, f in enumerate(fmc_files[:5]):  # Show first 5
                logging.info(f"  {i+1}. {f}")
            if len(fmc_files) > 5:
                logging.info(f"  ... and {len(fmc_files)-5} more")
    except Exception as e:
        logging.error(f"Error during debug file listing: {e}")
 
def find_rpt_files(root_path, corners, types):
    """
    Find all RPT files that match the FMC sigma pattern: fmc*{corner}*{type}*.rpt
 
    Args:
        root_path: Root directory to search in
        corners: List of corner names
        types: List of type names
 
    Returns:
        dict: Dictionary mapping (corner, type) to file path
    """
    logging.info(f"Searching for sigma RPT files in: {root_path}")
 
    found_files = {}
 
    try:
        all_files = os.listdir(root_path)
        # Look for FMC files with the simple pattern
        rpt_files = [f for f in all_files if f.endswith('.rpt') and 'fmc' in f.lower()]
        logging.info(f"Found {len(rpt_files)} FMC RPT files in directory")
        logging.debug(f"All FMC RPT files: {rpt_files}")
    except Exception as e:
        logging.error(f"Error listing files in directory: {root_path}", exc_info=True)
        return found_files
 
    for corner in corners:
        for type_name in types:
            matching_files = []
 
            # Simple pattern: fmc*{corner}*{type}*.rpt
            for f in rpt_files:
                if corner in f and type_name in f:
                    matching_files.append(f)
 
            if matching_files:
                file_path = os.path.join(root_path, matching_files[0])
                found_files[(corner, type_name)] = file_path
                logging.info(f"Matched sigma file for {corner}*{type_name}: {matching_files[0]}")
 
                if len(matching_files) > 1:
                    logging.warning(f"Multiple matches for {corner}*{type_name}: {matching_files}")
            else:
                logging.warning(f"No sigma file found for {corner}*{type_name}")
                logging.debug(f"  Available files containing '{corner}': {[f for f in rpt_files if corner in f]}")
 
    logging.info(f"Total matching sigma files found: {len(found_files)}")
    return found_files
 
def process_sigma_file(file_path, type_name):
    """
    Process a single sigma RPT file and generate the output file with check information
 
    Args:
        file_path: Path to the input RPT file
        type_name: 'delay', 'slew', or 'hold'
 
    Returns:
        str: Path to the output file
    """
    # Setup logging for this file
    log_file = setup_logging(file_path)
    logging.info(f"="*80)
    logging.info(f"Starting to process sigma file {file_path}")
    logging.info(f"Type: {type_name}")
    logging.info(f"="*80)
 
    try:
        # Read the RPT file
        logging.info(f"Reading sigma RPT file: {file_path}")
 
        # Read as CSV directly (since it's from our enhanced combine script)
        df = pd.read_csv(file_path)
        logging.info(f"Sigma CSV parsed successfully. Shape: {df.shape}")
 
        # Log column headers to verify correct structure
        logging.debug(f"CSV columns: {list(df.columns)}")
 
        # Detect vendor (CDNS or SNPS) from column names
        vendor_prefix = detect_vendor_columns(df)
        logging.info(f"Using vendor prefix: {vendor_prefix}")
 
        # Check if required columns exist
        required_columns = ['Arc', 'rel_pin_slew']
 
        # Determine which sigma parameters to check based on type
        if type_name in ['delay', 'slew']:
            sigma_params = ['Early_Sigma', 'Late_Sigma']
        else:  # hold
            sigma_params = ['Late_Sigma']
 
        for param in sigma_params:
            required_columns.extend([
                f'MC_{param}', f'{vendor_prefix}_{param}',
                f'{vendor_prefix}_{param}_Dif', f'{vendor_prefix}_{param}_Rel',
                f'MC_{param}_LB', f'MC_{param}_UB'  # CI bounds for enlargement
            ])
 
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            logging.error(f"Missing required columns: {missing_columns}")
            return None
 
        # Create output dataframe
        logging.info("Creating sigma output dataframe")
        result_df = pd.DataFrame()
        result_df['Arc'] = df['Arc']
 
        # Log first few rows of input data
        logging.debug(f"First 3 rows of input data:\n{df.head(3)}")
 
        # Process each sigma parameter with tier tracking
        tier_summary = {}  # Track tier-by-tier statistics
 
        for param in sigma_params:
            logging.info(f"Processing sigma parameter: {param}")
 
            # Initialize tracking lists
            tier1_list = []
            tier2_list = []
            tier3_list = []
            tier4_list = []
            overall_pass_list = []
            pass_reason_list = []
 
            # Tier statistics
            tier_stats = {
                'tier1_only': 0, 'tier2_cumulative': 0, 'tier3_cumulative': 0, 'tier4_cumulative': 0,
                'total_arcs': 0
            }
 
            for idx, row in df.iterrows():
                arc_name = row['Arc']
                logging.debug(f"Processing row {idx}, Arc: {arc_name}")
 
                tier_results = check_sigma_pass_fail_with_tiers(row, type_name, param, vendor_prefix)
 
                # Extract results
                tier1_pass = tier_results['tier1_pass']
                tier2_pass = tier_results['tier2_pass']
                tier3_pass = tier_results['tier3_pass']
                tier4_pass = tier_results['tier4_pass']
                overall_pass = tier_results['overall_pass']
                pass_reason = tier_results['pass_reason']
 
                # Convert to strings for CSV
                tier1_list.append("Pass" if tier1_pass else "Fail")
                tier2_list.append("Pass" if tier2_pass else "Fail")
                tier3_list.append("Pass" if tier3_pass else "Fail")
                tier4_list.append("Pass" if tier4_pass else "Fail")
                overall_pass_list.append("Pass" if overall_pass else "Fail")
                pass_reason_list.append(pass_reason)
 
                # Update tier statistics
                tier_stats['total_arcs'] += 1
                if tier1_pass:
                    tier_stats['tier1_only'] += 1
                if tier1_pass or tier2_pass:
                    tier_stats['tier2_cumulative'] += 1
                if tier1_pass or tier2_pass or tier3_pass:
                    tier_stats['tier3_cumulative'] += 1
                if tier1_pass or tier2_pass or tier3_pass or tier4_pass:
                    tier_stats['tier4_cumulative'] += 1
 
                logging.debug(f"  Results for {arc_name}, {param}: T1={tier1_pass}, T2={tier2_pass}, T3={tier3_pass}, T4={tier4_pass}, overall={overall_pass}, reason={pass_reason}")
 
            # Add columns to result dataframe
            result_df[f'{param}_tier1'] = tier1_list
            result_df[f'{param}_tier2'] = tier2_list
            result_df[f'{param}_tier3'] = tier3_list
            result_df[f'{param}_tier4'] = tier4_list
            result_df[f'{param}'] = overall_pass_list
            result_df[f'{param}_reason'] = pass_reason_list
 
            # Calculate pass rates for each tier
            total_count = tier_stats['total_arcs']
            if total_count > 0:
                tier1_rate = (tier_stats['tier1_only'] / total_count) * 100
                tier2_rate = (tier_stats['tier2_cumulative'] / total_count) * 100
                tier3_rate = (tier_stats['tier3_cumulative'] / total_count) * 100
                tier4_rate = (tier_stats['tier4_cumulative'] / total_count) * 100
 
                tier_summary[param] = {
                    'tier1_only': tier1_rate,
                    'tier2_cumulative': tier2_rate,
                    'tier3_cumulative': tier3_rate,
                    'tier4_cumulative': tier4_rate,
                    'total_arcs': total_count
                }
 
                # Log detailed tier statistics (1 digit precision)
                logging.info(f"  {param} Tier Analysis:")
                logging.info(f"    Tier 1 only (rel_tol): {tier_stats['tier1_only']}/{total_count} ({tier1_rate:.1f}%)")
                logging.info(f"    Tier 1+2 (+ CI bounds): {tier_stats['tier2_cumulative']}/{total_count} ({tier2_rate:.1f}%)")
                logging.info(f"    Tier 1+2+3 (+ CI enlarged): {tier_stats['tier3_cumulative']}/{total_count} ({tier3_rate:.1f}%)")
                logging.info(f"    Tier 1+2+3+4 (+ abs_tol): {tier_stats['tier4_cumulative']}/{total_count} ({tier4_rate:.1f}%)")
 
                # Final pass rate (same as tier4_cumulative)
                pass_count = overall_pass_list.count("Pass")
                final_pass_rate = (pass_count / total_count) * 100
                logging.info(f"    Final pass rate: {pass_count}/{total_count} ({final_pass_rate:.1f}%)")
 
        # Save tier summary for this file
        if hasattr(process_sigma_file, 'tier_summaries'):
            process_sigma_file.tier_summaries[(os.path.basename(file_path), type_name)] = tier_summary
        else:
            process_sigma_file.tier_summaries = {(os.path.basename(file_path), type_name): tier_summary}
 
        # Determine output file path - change .rpt to _sigma_check_info.csv
        output_file = file_path.replace('.rpt', '_sigma_check_info.csv')
 
        # Log summary of output dataframe
        logging.debug(f"Output dataframe preview:\n{result_df.head(3)}")
        logging.info(f"Output columns: {list(result_df.columns)}")
 
        # Save to CSV
        logging.info(f"Saving sigma output to: {output_file}")
        result_df.to_csv(output_file, index=False)
        logging.info(f"Sigma output saved successfully")
 
        return output_file
 
    except Exception as e:
        logging.error(f"Error processing {file_path}", exc_info=True)
        return None
 
def create_tier_visualization(root_path):
    """
    Create exactly two clean tier analysis visualizations: Early_Sigma and Late_Sigma
    Each combines all types and corners with proper grouping
    """
    if not hasattr(process_sigma_file, 'tier_summaries'):
        logging.warning("No tier summary data available for visualization")
        return None
 
    tier_summaries = process_sigma_file.tier_summaries
 
    try:
        import matplotlib
        matplotlib.use('Agg')  # Use non-interactive backend
        import matplotlib.pyplot as plt
        import numpy as np
 
        # Set style for better aesthetics
        plt.style.use('seaborn-v0_8-whitegrid')
 
        # Color scheme for tiers
        tier_colors = {
            'tier1_only': '#27ae60',      # Green - strict pass
            'tier2_improvement': '#3498db',   # Blue - CI bounds help
            'tier3_improvement': '#f39c12',   # Orange - CI enlarged help
            'tier4_improvement': '#e74c3c',   # Red - abs tolerance help
            'remaining_fail': '#95a5a6'       # Gray - still failing
        }
 
        # Set font properties for better readability
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
        plt.rcParams['font.size'] = 12
        plt.rcParams['axes.titlesize'] = 16
        plt.rcParams['axes.labelsize'] = 14
 
        # Improved corner extraction function
        def extract_corner_from_filename(file_name):
            """Extract full corner name from filename like fmc*ssgnp_0p450v_m40c*type*.rpt"""
            base_name = file_name.replace('.rpt', '').replace('fmc_', '')
 
            import re
            corner_pattern = r'(ssg[ng][pg]_[0-9]p[0-9]+v_[mn][0-9]+c)'
            match = re.search(corner_pattern, base_name)
            if match:
                return match.group(1)
 
            parts = base_name.split('_')
            corner_parts = []
            for i, part in enumerate(parts):
                if 'ssgnp' in part or 'ssgng' in part:
                    corner_parts = parts[i:i+3] if i+3 <= len(parts) else parts[i:]
                    break
 
            if corner_parts:
                return '_'.join(corner_parts)
 
            return '_'.join(base_name.split('_')[:3])
 
        # Organize data by corner and type with improved extraction
        data_by_corner_type = {}
        for (file_name, type_name), param_data in tier_summaries.items():
            corner = extract_corner_from_filename(file_name)
            logging.info(f"Extracted corner '{corner}' from file '{file_name}'")
 
            if corner not in data_by_corner_type:
                data_by_corner_type[corner] = {}
            data_by_corner_type[corner][type_name] = param_data
 
        visualization_files = []
 
        # Create exactly two visualizations: Early_Sigma and Late_Sigma
        for sigma_param in ['Early_Sigma', 'Late_Sigma']:
            logging.info(f"Creating visualization for: {sigma_param}")
 
            # Collect all data for this sigma parameter
            plot_data = []
            labels = []
            type_groups = []
 
            # Determine which types have this parameter
            if sigma_param == 'Early_Sigma':
                applicable_types = ['delay', 'slew']  # Early_Sigma only for delay and slew
            else:  # Late_Sigma
                applicable_types = ['delay', 'slew', 'hold']  # Late_Sigma for all types
 
            # Sort types for consistent ordering
            applicable_types = sorted(applicable_types)
 
            # Collect data for each type-corner combination
            for type_name in applicable_types:
                for corner in sorted(data_by_corner_type.keys()):
                    if (type_name in data_by_corner_type[corner] and
                        sigma_param in data_by_corner_type[corner][type_name]):
 
                        stats = data_by_corner_type[corner][type_name][sigma_param]
 
                        # Calculate incremental improvements
                        tier1_only = stats['tier1_only']
                        tier2_improvement = stats['tier2_cumulative'] - stats['tier1_only']
                        tier3_improvement = stats['tier3_cumulative'] - stats['tier2_cumulative']
                        tier4_improvement = stats['tier4_cumulative'] - stats['tier3_cumulative']
                        remaining_fail = 100 - stats['tier4_cumulative']
 
                        plot_data.append([tier1_only, tier2_improvement, tier3_improvement, tier4_improvement, remaining_fail])
 
                        # Create clean labels
                        corner_short = corner.replace('ssgnp_', '').replace('ssgng_', '').replace('_m40c', '')
                        labels.append(f"{type_name.upper()}\n{corner_short}")
                        type_groups.append(type_name)
 
            if not plot_data:
                logging.warning(f"No data found for {sigma_param}")
                continue
 
            # Create single plot for this sigma parameter
            fig, ax = plt.subplots(figsize=(max(16, len(labels) * 1.2), 10))
 
            plot_data = np.array(plot_data)
            x = np.arange(len(labels))
            width = 0.7
 
            # Create stacked bars
            bottom = np.zeros(len(labels))
 
            colors = [tier_colors['tier1_only'], tier_colors['tier2_improvement'],
                     tier_colors['tier3_improvement'], tier_colors['tier4_improvement'],
                     tier_colors['remaining_fail']]
            tier_labels = ['Tier 1 (Relative)', 'Tier 2 (CI Bounds)', 'Tier 3 (CI +6%)', 'Tier 4 (Absolute)', 'Failed']
 
            bars = []
            for i, (color, label) in enumerate(zip(colors, tier_labels)):
                bars.append(ax.bar(x, plot_data[:, i], width, bottom=bottom,
                                  color=color, label=label, alpha=0.9,
                                  edgecolor='white', linewidth=1.5))
                bottom += plot_data[:, i]
 
            # Add value labels on segments > 2%
            for i, label in enumerate(labels):
                y_pos = 0
                for j in range(5):
                    segment_height = plot_data[i, j]
                    if segment_height > 2:
                        text_color = 'white' if j < 4 else 'black'
                        ax.text(i, y_pos + segment_height/2, f'{segment_height:.1f}%',
                               ha='center', va='center', fontweight='bold',
                               color=text_color, fontsize=11)
                    y_pos += segment_height
 
            # Add type separators with alternating background colors
            current_type = None
            type_start = 0
            for i, group_type in enumerate(type_groups):
                if current_type != group_type:
                    if current_type is not None:
                        # Add background color for previous type group
                        if applicable_types.index(current_type) % 2 == 0:
                            ax.axvspan(type_start - 0.5, i - 0.5, alpha=0.05, color='blue', zorder=0)
                    current_type = group_type
                    type_start = i
 
            # Add background for last type group
            if current_type and applicable_types.index(current_type) % 2 == 0:
                ax.axvspan(type_start - 0.5, len(labels) - 0.5, alpha=0.05, color='blue', zorder=0)
 
            # Add vertical separators between type groups
            current_type = None
            for i, group_type in enumerate(type_groups):
                if current_type != group_type and current_type is not None:
                    ax.axvline(x=i - 0.5, color='black', linestyle='-', alpha=0.3, linewidth=2)
                current_type = group_type
 
            # Customize the plot with better spacing
            ax.set_title(f'{sigma_param.replace("_", " ")} - Four-Tier Pass Rate Analysis\n' +
                        f'Grouped by Type â†’ Corner | Target: 95% Pass Rate',
                        fontweight='bold', pad=30, fontsize=18)  # Increased pad to avoid overlap
            ax.set_ylabel('Pass Rate (%)', fontweight='bold', fontsize=14)
            ax.set_ylim(0, 105)  # Give more space at top
            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=11)
 
            # Add horizontal line at 95% target with better positioning
            ax.axhline(y=95, color='red', linestyle='--', alpha=0.8, linewidth=2)
            ax.text(len(labels) * 0.02, 97, '95% Target', ha='left', va='bottom',
                   color='red', fontweight='bold', fontsize=12,
                   bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.9))
 
            # Add larger, better positioned legend
            legend = ax.legend(loc='center right', fontsize=13, title='Tier Contributions',
                             title_fontsize=14, bbox_to_anchor=(0.98, 0.7),
                             framealpha=0.95, edgecolor='black')
            legend.get_title().set_fontweight('bold')
 
            # Add grid
            ax.grid(True, axis='y', alpha=0.3, linestyle=':')
            ax.set_axisbelow(True)
 
            # Highlight failing cases
            for i, group_type in enumerate(type_groups):
                final_pass_rate = np.sum(plot_data[i, :4])
                if final_pass_rate < 95:
                    ax.axvspan(i-width/2, i+width/2, alpha=0.2, color='red', zorder=0)
                    # Add failure indicator below
                    ax.text(i, 2, f'{final_pass_rate:.1f}%', ha='center', va='center',
                           fontweight='bold', color='red', fontsize=10,
                           bbox=dict(boxstyle="round,pad=0.2", facecolor='white', alpha=0.9))
 
            # Add type labels at the top
            current_type = None
            type_start = 0
            type_positions = []
            type_names = []
 
            for i, group_type in enumerate(type_groups):
                if current_type != group_type:
                    if current_type is not None:
                        # Calculate center position for previous type
                        center_pos = (type_start + i - 1) / 2
                        type_positions.append(center_pos)
                        type_names.append(current_type.upper())
                    current_type = group_type
                    type_start = i
 
            # Add the last type
            if current_type:
                center_pos = (type_start + len(labels) - 1) / 2
                type_positions.append(center_pos)
                type_names.append(current_type.upper())
 
            # Add type labels with background
            for pos, name in zip(type_positions, type_names):
                ax.text(pos, 102, name, ha='center', va='center', fontweight='bold',
                       fontsize=14, color='navy',
                       bbox=dict(boxstyle="round,pad=0.5", facecolor='lightblue', alpha=0.8))
 
            # Adjust layout
            plt.tight_layout()
 
            # Save individual visualization - FIXED FILE NAMING
            sigma_vis_file = os.path.join(root_path, f"sigma_{sigma_param.lower()}_tier_analysis.png")
            plt.savefig(sigma_vis_file, dpi=300, bbox_inches='tight', facecolor='white')
            logging.info(f"{sigma_param} tier analysis saved to: {sigma_vis_file}")
            visualization_files.append(sigma_vis_file)
 
            plt.close(fig)
 
        # Also create clean heatmap
        create_clean_tier_heatmap(root_path, data_by_corner_type)
 
        return visualization_files
 
    except ImportError as e:
        logging.error(f"Could not create tier visualization: {str(e)}")
        logging.info("Please install matplotlib to enable visualizations")
        return None
    except Exception as e:
        logging.error(f"Error creating tier visualization", exc_info=True)
        return None
 
def create_clean_tier_heatmap(root_path, data_by_corner_type):
    """
    Create a clean heatmap summary showing final pass rates only
    """
    try:
        import matplotlib.pyplot as plt
        import numpy as np
 
        # Collect all data for heatmap
        corners = sorted(data_by_corner_type.keys())
        corner_labels = [c.replace('ssgnp_', '').replace('ssgng_', '').replace('_m40c', '') for c in corners]
 
        # Get all type-parameter combinations
        type_param_combos = []
        for corner_data in data_by_corner_type.values():
            for type_name, type_data in corner_data.items():
                for param in type_data.keys():
                    combo = f"{type_name}_{param}"
                    if combo not in type_param_combos:
                        type_param_combos.append(combo)
 
        type_param_combos = sorted(type_param_combos)
 
        # Create matrix
        matrix = np.zeros((len(corners), len(type_param_combos)))
 
        for i, corner in enumerate(corners):
            for j, combo in enumerate(type_param_combos):
                type_name, param = combo.split('_', 1)
                if (type_name in data_by_corner_type[corner] and
                    param in data_by_corner_type[corner][type_name]):
                    matrix[i, j] = data_by_corner_type[corner][type_name][param]['tier4_cumulative']
                else:
                    matrix[i, j] = np.nan
 
        # Create heatmap
        fig, ax = plt.subplots(figsize=(12, 8))
 
        im = ax.imshow(matrix, cmap='RdYlGn', aspect='auto', vmin=90, vmax=100)
        plt.colorbar(im, ax=ax, label='Final Pass Rate (%)')
 
        # Set labels
        ax.set_title('Sigma Pass Rate Summary Heatmap\n(Final Pass Rate After All Tiers)',
                    fontweight='bold', pad=20, fontsize=16)
        ax.set_xticks(range(len(type_param_combos)))
        ax.set_xticklabels([combo.replace('_', '\n') for combo in type_param_combos],
                          rotation=0, ha='center', fontsize=10)
        ax.set_yticks(range(len(corners)))
        ax.set_yticklabels(corner_labels, fontsize=11)
 
        # Add text annotations
        for i in range(len(corners)):
            for j in range(len(type_param_combos)):
                if not np.isnan(matrix[i, j]):
                    color = 'white' if matrix[i, j] < 95 else 'black'
                    weight = 'bold' if matrix[i, j] < 95 else 'normal'
                    ax.text(j, i, f'{matrix[i, j]:.1f}%', ha='center', va='center',
                           color=color, fontweight=weight, fontsize=10)
 
        plt.tight_layout()
 
        # Save heatmap
        heatmap_file = os.path.join(root_path, "sigma_pass_rate_heatmap.png")
        plt.savefig(heatmap_file, dpi=300, bbox_inches='tight', facecolor='white')
        logging.info(f"Clean sigma heatmap saved to: {heatmap_file}")
 
        plt.close(fig)
        return heatmap_file
 
    except Exception as e:
        logging.error(f"Error creating clean heatmap: {e}")
        return None
 
def generate_tier_analysis_report(root_path):
    """
    Generate detailed tier-by-tier analysis report with 1-digit precision
    """
    if not hasattr(process_sigma_file, 'tier_summaries'):
        logging.warning("No tier summary data available")
        return None
 
    tier_summaries = process_sigma_file.tier_summaries
 
    # Create tier analysis report
    tier_report = []
    tier_report.append("="*80)
    tier_report.append("DETAILED TIER-BY-TIER PASS RATE ANALYSIS (1-digit precision)")
    tier_report.append("="*80)
    tier_report.append("")
    tier_report.append("Four-Tier Checking System:")
    tier_report.append("  Tier 1: Relative error <= threshold")
    tier_report.append("  Tier 2: Tier 1 + Value within original CI bounds")
    tier_report.append("  Tier 3: Tier 2 + Value within CI + 6% enlargement")
    tier_report.append("  Tier 4: Tier 3 + Absolute error <= slew-dependent threshold")
    tier_report.append("")
 
    for (file_name, type_name), param_data in tier_summaries.items():
        tier_report.append(f"File: {file_name} ({type_name.upper()})")
        tier_report.append("-" * 60)
 
        for param, stats in param_data.items():
            tier_report.append(f"\n{param} Analysis:")
            tier_report.append(f"  Total arcs: {stats['total_arcs']}")
            tier_report.append(f"  Tier 1 only (rel_tol):        {stats['tier1_only']:.1f}%")
            tier_report.append(f"  Tier 1+2 (+ CI bounds):       {stats['tier2_cumulative']:.1f}%")
            tier_report.append(f"  Tier 1+2+3 (+ CI enlarged):   {stats['tier3_cumulative']:.1f}%")
            tier_report.append(f"  Tier 1+2+3+4 (+ abs_tol):     {stats['tier4_cumulative']:.1f}%")
 
            # Calculate incremental improvements
            tier2_improvement = stats['tier2_cumulative'] - stats['tier1_only']
            tier3_improvement = stats['tier3_cumulative'] - stats['tier2_cumulative']
            tier4_improvement = stats['tier4_cumulative'] - stats['tier3_cumulative']
 
            tier_report.append(f"\n  Incremental Improvements:")
            tier_report.append(f"    CI bounds added:      +{tier2_improvement:.1f}%")
            tier_report.append(f"    CI enlargement added: +{tier3_improvement:.1f}%")
            tier_report.append(f"    Absolute tol added:   +{tier4_improvement:.1f}%")
 
        tier_report.append("")
 
    # Save tier analysis report
    tier_analysis_file = os.path.join(root_path, "sigma_tier_analysis.txt")
    with open(tier_analysis_file, 'w') as f:
        f.write('\n'.join(tier_report))
 
    logging.info(f"Tier analysis report saved to: {tier_analysis_file}")
 
    # Print to console
    print('\n' + '\n'.join(tier_report))
 
    return tier_analysis_file
 
def generate_sigma_pr_table(results, root_path):
    """
    Generate sigma PR table in the format expected by check_moments.py (includes hold)
 
    Args:
        results: Dictionary with (corner, type) keys and pass rate dictionaries as values
        root_path: Root directory path to save the sigma PR table
 
    Returns:
        str: Path to the sigma PR table file
    """
    logging.info("Generating sigma PR table (includes hold)")
 
    # Create dataframe for sigma PR table
    sigma_pr_data = []
 
    # Collect all corners and types
    all_corners = set()
    all_types = set()
 
    for (corner, type_name) in results.keys():
        all_corners.add(corner)
        all_types.add(type_name)
 
    for corner in sorted(all_corners):
        for type_name in sorted(all_types):
            if (corner, type_name) in results:
                rates = results[(corner, type_name)]
 
                # Create row for sigma PR table
                row = {
                    'Corner': corner,
                    'Type': type_name,
                    'early_sigma': rates.get('Early_Sigma', 0),
                    'late_sigma': rates.get('Late_Sigma', 0)
                }
                sigma_pr_data.append(row)
            else:
                # Add empty row if no data
                row = {
                    'Corner': corner,
                    'Type': type_name,
                    'early_sigma': 0,
                    'late_sigma': 0
                }
                sigma_pr_data.append(row)
 
    # Create DataFrame and save
    sigma_pr_df = pd.DataFrame(sigma_pr_data)
 
    # Save to CSV
    sigma_pr_file = os.path.join(root_path, "sigma_PR_table.csv")
    sigma_pr_df.to_csv(sigma_pr_file, index=False)
    logging.info(f"Sigma PR table saved to: {sigma_pr_file}")
 
    return sigma_pr_file
 
def generate_sigma_pr_table_moments_only(results, root_path):
    """
    Generate sigma PR table for moments integration (excludes hold, only delay and slew)
 
    Args:
        results: Dictionary with (corner, type) keys and pass rate dictionaries as values
        root_path: Root directory path to save the sigma PR table
 
    Returns:
        str: Path to the sigma PR table file
    """
    logging.info("Generating sigma PR table for moments (delay and slew only)")
 
    # Create dataframe for sigma PR table
    sigma_pr_data = []
 
    # Collect all corners and types, but filter to only delay and slew
    all_corners = set()
    moments_types = set()
 
    for (corner, type_name) in results.keys():
        if type_name in ['delay', 'slew']:  # Only include delay and slew for moments
            all_corners.add(corner)
            moments_types.add(type_name)
 
    for corner in sorted(all_corners):
        for type_name in sorted(moments_types):
            if (corner, type_name) in results:
                rates = results[(corner, type_name)]
 
                # Create row for sigma PR table
                row = {
                    'Corner': corner,
                    'Type': type_name,
                    'early_sigma': rates.get('Early_Sigma', 0),
                    'late_sigma': rates.get('Late_Sigma', 0)
                }
                sigma_pr_data.append(row)
            else:
                # Add empty row if no data
                row = {
                    'Corner': corner,
                    'Type': type_name,
                    'early_sigma': 0,
                    'late_sigma': 0
                }
                sigma_pr_data.append(row)
 
    # Create DataFrame and save
    sigma_pr_df = pd.DataFrame(sigma_pr_data)
 
    # Save to CSV
    sigma_pr_file = os.path.join(root_path, "sigma_PR_table_moments.csv")
    sigma_pr_df.to_csv(sigma_pr_file, index=False)
    logging.info(f"Sigma PR table for moments saved to: {sigma_pr_file}")
    logging.info(f"Excluded hold data - only delay and slew included for moments integration")
 
    return sigma_pr_file
 
def generate_sigma_summary_table(results, root_path):
    """
    Generate a summary table of sigma pass rates for each corner and type (1-digit precision)
 
    Args:
        results: Dictionary with (corner, type) keys and pass rate dictionaries as values
        root_path: Root directory path to save the summary file
 
    Returns:
        str: Path to the summary file
    """
    logging.info("Generating sigma summary table")
 
    # Create dataframes for each type
    delay_df = pd.DataFrame(columns=[
        'Corner',
        'Early_Sigma PR', 'Early_Sigma Status',
        'Late_Sigma PR', 'Late_Sigma Status'
    ])
 
    slew_df = pd.DataFrame(columns=[
        'Corner',
        'Early_Sigma PR', 'Early_Sigma Status',
        'Late_Sigma PR', 'Late_Sigma Status'
    ])
 
    hold_df = pd.DataFrame(columns=[
        'Corner',
        'Late_Sigma PR', 'Late_Sigma Status'
    ])
 
    # Set the pass threshold
    pass_threshold = 95.0  # 95%
 
    # Fill the dataframes
    all_corners = set()
    all_types = set()
 
    # Collect all corners and types
    for (corner, type_name) in results.keys():
        all_corners.add(corner)
        all_types.add(type_name)
 
    for corner in sorted(all_corners):
        for type_name in sorted(all_types):
            # Start with an empty row
            new_row = {'Corner': corner}
 
            # Add sigma results
            if (corner, type_name) in results:
                rates = results[(corner, type_name)]
 
                if type_name in ['delay', 'slew']:
                    for param in ['Early_Sigma', 'Late_Sigma']:
                        rate = rates.get(param, 0)
                        new_row[f'{param} PR'] = rate
                        new_row[f'{param} Status'] = 'Pass' if rate >= pass_threshold else 'Fail'
                else:  # hold
                    param = 'Late_Sigma'
                    rate = rates.get(param, 0)
                    new_row[f'{param} PR'] = rate
                    new_row[f'{param} Status'] = 'Pass' if rate >= pass_threshold else 'Fail'
            else:
                if type_name in ['delay', 'slew']:
                    for param in ['Early_Sigma', 'Late_Sigma']:
                        new_row[f'{param} PR'] = 0
                        new_row[f'{param} Status'] = 'N/A'
                else:  # hold
                    new_row['Late_Sigma PR'] = 0
                    new_row['Late_Sigma Status'] = 'N/A'
 
            # Add to the appropriate dataframe
            if type_name == 'delay':
                delay_df = pd.concat([delay_df, pd.DataFrame([new_row])], ignore_index=True)
            elif type_name == 'slew':
                slew_df = pd.concat([slew_df, pd.DataFrame([new_row])], ignore_index=True)
            else:  # hold
                hold_df = pd.concat([hold_df, pd.DataFrame([new_row])], ignore_index=True)
 
    # Format for better display (1-digit precision)
    for df in [delay_df, slew_df, hold_df]:
        if not df.empty:
            for col in df.columns:
                if 'PR' in col:
                    df[col] = df[col].map('{:.1f}%'.format)
 
    # Create the summary string
    summary = "Sigma Summary Table (1-digit precision)\n"
    summary += "\nDelay:\n"
    summary += delay_df.to_string(index=False) if not delay_df.empty else "No delay data"
    summary += "\n\nSlew:\n"
    summary += slew_df.to_string(index=False) if not slew_df.empty else "No slew data"
    summary += "\n\nHold:\n"
    summary += hold_df.to_string(index=False) if not hold_df.empty else "No hold data"
 
    # Save to file
    summary_file = os.path.join(root_path, "sigma_summary_table.txt")
    with open(summary_file, 'w') as f:
        f.write(summary)
 
    logging.info(f"Sigma summary table saved to: {summary_file}")
 
    # Also create a CSV version for easier processing
    csv_file = os.path.join(root_path, "sigma_summary_table.csv")
 
    # Combine dataframes with a Type column
    delay_df['Type'] = 'delay'
    slew_df['Type'] = 'slew'
    hold_df['Type'] = 'hold'
    combined_df = pd.concat([delay_df, slew_df, hold_df], ignore_index=True)
 
    # Save to CSV
    combined_df.to_csv(csv_file, index=False)
    logging.info(f"Sigma summary CSV saved to: {csv_file}")
 
    return summary_file, csv_file
 
def main():
    # Parse command line arguments
    args = parse_arguments()
 
    # Set up a main log file
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    main_log_file = f"sigma_check_{timestamp}.log"
 
    # Configure main logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(main_log_file),
            logging.StreamHandler()
        ]
    )
 
    logging.info("="*80)
    logging.info("Starting FINAL CORRECTED sigma check script with CI enlargement (CDNS/SNPS compatible)")
    logging.info(f"Main log file: {main_log_file}")
    logging.info("Four-tier checking: rel_threshold -> CI_bounds -> CI_enlarged -> abs_threshold")
    logging.info("GENERATES EXACTLY 2 PNG FILES: Early_Sigma and Late_Sigma tier analysis")
    logging.info("="*80)
 
    # Use arguments directly
    root_path = args.root_path
    corners = args.corners
    types = args.types
 
    logging.info("Parameters received:")
    logging.info(f"  Root path: {root_path}")
    logging.info(f"  Corners: {corners}")
    logging.info(f"  Types: {types}")
 
    # Check if root path exists
    if not os.path.exists(root_path):
        logging.error(f"Root path does not exist: {root_path}")
        return
 
    # Find matching RPT files
    rpt_files = find_rpt_files(root_path, corners, types)
 
    if not rpt_files:
        logging.error("No matching sigma RPT files found!")
        debug_available_files(root_path)
        return
 
    # Process each found file
    successful_files = []
    failed_files = []
 
    # Dictionary to store pass rates for summary table
    sigma_pass_rates = {}
 
    for (corner, type_name), file_path in rpt_files.items():
        logging.info(f"Processing sigma {corner} - {type_name}: {file_path}")
        result = process_sigma_file(file_path, type_name)
 
        if result:
            successful_files.append(file_path)
 
            # Calculate pass rates for this file
            try:
                output_df = pd.read_csv(result)
                file_rates = {}
 
                # Determine which parameters to check based on type
                if type_name in ['delay', 'slew']:
                    params = ['Early_Sigma', 'Late_Sigma']
                else:  # hold
                    params = ['Late_Sigma']
 
                for param in params:
                    passes = (output_df[param] == 'Pass').sum()
                    total = len(output_df)
                    rate = (passes / total) * 100 if total > 0 else 0
                    file_rates[param] = rate
                    logging.info(f"  {param} pass rate: {passes}/{total} ({rate:.1f}%)")
 
                # Store rates for summary table
                sigma_pass_rates[(corner, type_name)] = file_rates
 
            except Exception as e:
                logging.error(f"Error calculating pass rates for {file_path}", exc_info=True)
        else:
            failed_files.append(file_path)
 
    # Log summary
    logging.info("="*80)
    logging.info("Processing summary:")
    logging.info(f"  Total files found: {len(rpt_files)}")
    logging.info(f"  Successfully processed: {len(successful_files)}")
    logging.info(f"  Failed to process: {len(failed_files)}")
 
    if failed_files:
        logging.info("Failed files:")
        for file in failed_files:
            logging.info(f"    {file}")
 
    # Generate sigma PR table and summary
    if sigma_pass_rates:
        logging.info("Generating sigma outputs")
 
        # Generate tier analysis report (1-digit precision)
        tier_analysis_file = generate_tier_analysis_report(root_path)
        if tier_analysis_file:
            logging.info(f"Tier analysis report saved to: {tier_analysis_file}")
 
        # Generate exactly TWO visualization files
        vis_files = create_tier_visualization(root_path)
        if vis_files:
            logging.info(f"Generated {len(vis_files)} tier analysis visualizations:")
            for vis_file in vis_files:
                logging.info(f"  - {vis_file}")
 
        # Generate BOTH sigma PR tables
        sigma_pr_file = generate_sigma_pr_table(sigma_pass_rates, root_path)
        sigma_pr_moments_file = generate_sigma_pr_table_moments_only(sigma_pass_rates, root_path)
 
        # Generate summary tables (1-digit precision)
        summary_file, csv_file = generate_sigma_summary_table(sigma_pass_rates, root_path)
 
        logging.info(f"Sigma PR table (all types) saved to: {sigma_pr_file}")
        logging.info(f"Sigma PR table (moments only) saved to: {sigma_pr_moments_file}")
        logging.info(f"Sigma summary table saved to: {summary_file}")
        logging.info(f"Sigma summary CSV saved to: {csv_file}")
 
        # Print summary to console
        with open(summary_file, 'r') as f:
            summary_content = f.read()
        print('\n' + "="*50)
        print("FINAL SIGMA SUMMARY TABLE (1-digit precision):")
        print(f"="*50)
        print(summary_content)
        print("="*50)
        print("Note: Waived results (CI enlarged) are treated as Pass")
        print("Four-tier checking: rel_threshold -> CI_bounds -> CI_enlarged -> abs_threshold")
        print(f"Generated exactly 2 PNG files for tier analysis")
        print("="*50)
    else:
        logging.warning("Could not generate sigma summary table - no valid results")
 
    logging.info("="*80)
    logging.info("FINAL CORRECTED sigma check script completed (CDNS/SNPS)")
    logging.info("Generated outputs:")
    logging.info("  - sigma_PR_table.csv (all types)")
    logging.info("  - sigma_PR_table_moments.csv (delay/slew only for moments)")
    logging.info("  - sigma_early_sigma_tier_analysis.png (DELAY + SLEW)")
    logging.info("  - sigma_late_sigma_tier_analysis.png (DELAY + SLEW + HOLD)")
    logging.info("  - sigma_pass_rate_heatmap.png (summary)")
 
if __name__ == "__main__":
    main()
