#!/usr/bin/env python3
 
import os
import pandas as pd
import numpy as np
import sys
import logging
import datetime
from pathlib import Path
 
"""
Enhanced Moments Pass Rate Calculation Script (Safe Version)
 
This script maintains the ORIGINAL VERIFIED pass rate calculation while adding:
1. Enhanced visualization with 3 separate PNG files (Std, Meanshift, Skew)
2. DELAY/SLEW grouping labels like sigma visualization
3. Additional two-tier criteria analysis for comparison (CI bounds + enlargement)
4. 1-digit precision formatting
5. Enhanced corner extraction
 
ORIGINAL LOGIC PRESERVED:
- rel_pass OR abs_pass (unchanged)
- All original thresholds (unchanged)
- Core check_pass_fail function (unchanged)
"""
 
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
 
def check_pass_fail(row, type_name, param_name):
    """
    ORIGINAL VERIFIED FUNCTION - DO NOT MODIFY
    Check if the parameter passes the criteria for both absolute and relative error
 
    Args:
        row: DataFrame row with all the data
        type_name: 'delay' or 'slew'
        param_name: 'Std', 'Skew', or 'Meanshift'
 
    Returns:
        tuple: (abs_pass, rel_pass, abs_err, rel_err)
    """
    arc_name = row['Arc']
    logging.debug(f"Checking {param_name} for Arc: {arc_name}")
 
    # Extract the necessary values
    rel_pin_slew = row['rel_pin_slew']
 
    # Extract NC and Lib values with error handling
    try:
        nc_value = row[f"MC_{param_name}"]
        lib_value = row[f"Lib_{param_name}"]
        abs_err = row[f"{param_name}_abs_err"]
        rel_err = row[f"{param_name}_rel_err"]
 
        logging.debug(f"  rel_pin_slew: {rel_pin_slew}")
        logging.debug(f"  MC_{param_name}: {nc_value}")
        logging.debug(f"  Lib_{param_name}: {lib_value}")
        logging.debug(f"  {param_name}_abs_err: {abs_err}")
        logging.debug(f"  {param_name}_rel_err: {rel_err}")
    except KeyError as e:
        logging.error(f"Missing column: {e}")
        return False, False, None, None
 
    # Set thresholds based on type - ORIGINAL THRESHOLDS PRESERVED
    if type_name == 'delay':
        meanshift_rel_threshold = 0.01  # 1%
        std_rel_threshold = 0.02        # 2%
        skew_rel_threshold = 0.05       # 5%
        ps_value = 1                    # 1ps for delay
        logging.debug(f"  Using delay thresholds: meanshift={meanshift_rel_threshold}, std={std_rel_threshold}, skew={skew_rel_threshold}, ps={ps_value}")
    else:  # slew
        meanshift_rel_threshold = 0.02  # 2%
        std_rel_threshold = 0.04        # 4%
        skew_rel_threshold = 0.10       # 10%
        ps_value = 2                    # 2ps for slew
        logging.debug(f"  Using slew thresholds: meanshift={meanshift_rel_threshold}, std={std_rel_threshold}, skew={skew_rel_threshold}, ps={ps_value}")
 
    # Set the appropriate threshold based on parameter
    if param_name == 'Meanshift':
        rel_threshold = meanshift_rel_threshold
    elif param_name == 'Std':
        rel_threshold = std_rel_threshold
    else:  # Skew
        rel_threshold = skew_rel_threshold
 
    logging.debug(f"  Selected rel_threshold for {param_name}: {rel_threshold}")
 
    # Check relative error - ORIGINAL LOGIC PRESERVED
    rel_pass = abs(rel_err) <= rel_threshold
    logging.debug(f"  Relative error check: |{rel_err}| <= {rel_threshold} ? {rel_pass}")
 
    # Check absolute error - ORIGINAL LOGIC PRESERVED
    abs_threshold = max(0.005 * rel_pin_slew, ps_value * 1e-12) # Convert ps to seconds
    abs_pass = abs(abs_err) <= abs_threshold
    logging.debug(f" Absolute error check : |{abs_err}| <= {abs_threshold} ? {abs_pass} (0.005 * slew = {0.005 * rel_pin_slew}, ps = {ps_value}ps) = {ps_value * 1e-12}")
    logging.debug(f"  Final result for {param_name}: abs_pass = {abs_pass} or rel_pass = {rel_pass}, overall_pass = {abs_pass or rel_pass}")
 
    return abs_pass, rel_pass, abs_err, rel_err
 
def check_additional_criteria(row, type_name, param_name):
    """
    NEW FUNCTION: Additional two-tier criteria analysis for comparison
    This is SEPARATE from the main pass/fail logic
 
    Args:
        row: DataFrame row with all the data
        type_name: 'delay' or 'slew'
        param_name: 'Std', 'Skew', or 'Meanshift'
 
    Returns:
        dict: Additional criteria results for comparison
    """
    try:
        nc_value = row[f"MC_{param_name}"]
        lib_value = row[f"Lib_{param_name}"]
 
        # Estimate CI bounds (this is just for comparison, not used in main logic)
        nc_value_abs = abs(nc_value)
        ci_width_percent = 0.1  # 10% of the value as CI width
        ci_lb = nc_value - nc_value_abs * ci_width_percent
        ci_ub = nc_value + nc_value_abs * ci_width_percent
 
        # CI bounds check
        ci_bounds_pass = (ci_lb <= lib_value <= ci_ub)
 
        # CI enlargement check (6% enlargement)
        ci_enlargement = 0.06
        ci_width = abs(ci_ub - ci_lb)
        ci_enlargement_amount = ci_width * ci_enlargement
        enlarged_lb = ci_lb - ci_enlargement_amount
        enlarged_ub = ci_ub + ci_enlargement_amount
        ci_enlarged_pass = (enlarged_lb <= lib_value <= enlarged_ub)
 
        return {
            'ci_bounds_pass': ci_bounds_pass,
            'ci_enlarged_pass': ci_enlarged_pass
        }
 
    except Exception as e:
        logging.debug(f"Error in additional criteria check: {e}")
        return {
            'ci_bounds_pass': False,
            'ci_enlarged_pass': False
        }
 
def enhanced_corner_extraction(file_name):
    """
    Enhanced corner extraction using regex (like sigma script)
    """
    base_name = file_name.replace('.rpt', '').replace('MC_', '')
 
    import re
    corner_pattern = r'(ssg[ng][pg]_[0-9]p[0-9]+v_[mn][0-9]+c)'
    match = re.search(corner_pattern, base_name)
    if match:
        return match.group(1)
 
    # Fallback to original logic
    parts = base_name.split('_')
    corner_parts = []
    for i, part in enumerate(parts):
        if 'ssgnp' in part or 'ssgng' in part:
            corner_parts = parts[i:i+3] if i+3 <= len(parts) else parts[i:]
            break
 
    if corner_parts:
        return '_'.join(corner_parts)
 
    return '_'.join(base_name.split('_')[:3])
 
def find_rpt_files(root_path, corners, types):
    """
    Find all RPT files that match the pattern *{corner}*{type}*.rpt
 
    Args:
        root_path: Root directory to search in
        corners: List of corner names
        types: List of type names
 
    Returns:
        dict: Dictionary mapping (corner, type) to file path
    """
    logging.info(f"Searching for RPT files in: {root_path}")
 
    found_files = {}
 
    try:
        all_files = os.listdir(root_path)
        rpt_files = [f for f in all_files if f.endswith('.rpt') and f.startswith('MC')]
        logging.info(f"Found {len(rpt_files)} RPT files in directory")
        logging.debug(f"All RPT files: {rpt_files}")
    except Exception as e:
        logging.error(f"Error listing files in directory: {root_path}", exc_info=True)
        return found_files
 
    for corner in corners:
        for type_name in types:
            matching_files = []
 
            for f in rpt_files:
                if corner in f and type_name in f:
                    matching_files.append(f)
 
            if matching_files:
                file_path = os.path.join(root_path, matching_files[0])
                found_files[(corner, type_name)] = file_path
                logging.info(f"Matched file for {corner}*{type_name}: {matching_files[0]}")
 
            if len(matching_files) > 1:
                logging.warning(f"Multiple matches for {corner}*{type_name}: {matching_files}")
 
        else:
            logging.warning(f"No file found matching pattern *{corner}*{type_name}*.rpt")
 
    logging.info(f"Total matching files found: {len(found_files)}")
    return found_files
 
def process_file(file_path, type_name):
    """
    Enhanced processing with additional criteria analysis
    ORIGINAL LOGIC PRESERVED - only adds extra columns for comparison
 
    Args:
        file_path: Path to the input RPT file
        type_name: 'delay' or 'slew'
 
    Returns:
        str: Path to the output file
    """
    # Setup logging for this file
    log_file = setup_logging(file_path)
    logging.info(f"="*80)
    logging.info(f"Starting to process enhanced {file_path}")
    logging.info(f"Type: {type_name}")
    logging.info(f"ORIGINAL LOGIC PRESERVED - Adding comparison features only")
    logging.info(f"="*80)
 
    try:
        # Read the RPT file
        logging.info(f"Reading RPT file: {file_path}")
 
        # Read the file and parse the data
        with open(file_path, 'r') as f:
            content = f.readlines()
 
        logging.info(f"RPT file loaded successfully. Lines: {len(content)}")
 
        # Try to parse the RPT file as CSV (comma-separated)
        try:
            # First, determine if there's a header row
            header_line = None
            data_lines = []
 
            for i, line in enumerate(content):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
 
                if 'Arc' in line and 'rel_pin_slew' in line:
                    header_line = line
                    logging.info(f"Found header at line {i+1}: {header_line}")
                elif header_line and ',' in line:
                    data_lines.append(line)
 
            if not header_line:
                logging.error("Header row not found in RPT file")
                return None
 
            # Create a temporary CSV file for processing
            temp_csv = file_path + ".temp.csv"
            with open(temp_csv, 'w') as f:
                f.write(header_line + '\n')
                for line in data_lines:
                    f.write(line + '\n')
 
            logging.info(f"Created temporary CSV file with {len(data_lines)} data rows")
 
            # Now read the CSV with pandas
            df = pd.read_csv(temp_csv)
            logging.info(f"CSV parsed successfully. Shape: {df.shape}")
 
            # Remove temporary file
            os.remove(temp_csv)
            logging.info("Removed temporary CSV file")
 
        except Exception as e:
            logging.error(f"Error parsing RPT file as CSV", exc_info=True)
            return None
 
        # Log column headers to verify correct structure
        logging.debug(f"CSV columns: {list(df.columns)}")
 
        # Check if required columns exist
        required_columns = ['Arc', 'rel_pin_slew']
        for param in ['Std', 'Skew', 'Meanshift']:
            required_columns.extend([
                f'MC_{param}', f'Lib_{param}',
                f'{param}_abs_err', f'{param}_rel_err'
            ])
 
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            logging.error(f"Missing required columns: {missing_columns}")
            return None
 
        # Create enhanced output dataframe
        logging.info("Creating enhanced output dataframe")
        result_df = pd.DataFrame()
        result_df['Arc'] = df['Arc']
 
        # Log first few rows of input data
        logging.debug(f"First 3 rows of input data:\n{df.head(3)}")
 
        # Process each parameter - ORIGINAL LOGIC + ADDITIONAL COMPARISON
        for param in ['Std', 'Skew', 'Meanshift']:
            logging.info(f"Processing parameter: {param}")
 
            # ORIGINAL LOGIC PRESERVED
            abs_pass_list = []
            rel_pass_list = []
            overall_pass_list = []
 
            # NEW: Additional criteria for comparison
            ci_bounds_list = []
            ci_enlarged_list = []
            pass_reason_list = []
 
            for idx, row in df.iterrows():
                arc_name = row['Arc']
                logging.debug(f"Processing row {idx}, Arc: {arc_name}")
 
                # ORIGINAL VERIFIED FUNCTION - UNCHANGED
                abs_pass, rel_pass, abs_err, rel_err = check_pass_fail(row, type_name, param)
 
                # ORIGINAL LOGIC PRESERVED
                abs_result = "Pass" if abs_pass else "Fail"
                rel_result = "Pass" if rel_pass else "Fail"
                overall_result = "Pass" if (abs_pass or rel_pass) else "Fail"
 
                abs_pass_list.append(abs_result)
                rel_pass_list.append(rel_result)
                overall_pass_list.append(overall_result)
 
                # NEW: Track pass reason for debugging (doesn't change logic)
                if abs_pass and rel_pass:
                    reason = "both"
                elif abs_pass:
                    reason = "abs_only"
                elif rel_pass:
                    reason = "rel_only"
                else:
                    reason = "fail"
                pass_reason_list.append(reason)
 
                # NEW: Additional criteria analysis for comparison
                additional_results = check_additional_criteria(row, type_name, param)
                ci_bounds_result = "Pass" if additional_results['ci_bounds_pass'] else "Fail"
                ci_enlarged_result = "Pass" if additional_results['ci_enlarged_pass'] else "Fail"
 
                ci_bounds_list.append(ci_bounds_result)
                ci_enlarged_list.append(ci_enlarged_result)
 
                logging.debug(f"  Results for {arc_name}, {param}: abs={abs_result}, rel={rel_result}, overall={overall_result}, reason={reason}")
                logging.debug(f"  Additional criteria: ci_bounds={ci_bounds_result}, ci_enlarged={ci_enlarged_result}")
 
            # Add ORIGINAL columns to result dataframe
            result_df[f'{param}_abs'] = abs_pass_list
            result_df[f'{param}_rel'] = rel_pass_list
            result_df[f'{param}'] = overall_pass_list
 
            # Add NEW comparison columns
            result_df[f'{param}_reason'] = pass_reason_list
            result_df[f'{param}_ci_bounds'] = ci_bounds_list
            result_df[f'{param}_ci_enlarged'] = ci_enlarged_list
 
            # Log statistics with 1-digit precision
            pass_count = overall_pass_list.count("Pass")
            total_count = len(overall_pass_list)
            pass_rate = (pass_count / total_count) * 100 if total_count > 0 else 0
 
            # Additional criteria statistics
            ci_bounds_count = ci_bounds_list.count("Pass")
            ci_enlarged_count = ci_enlarged_list.count("Pass")
            ci_bounds_rate = (ci_bounds_count / total_count) * 100 if total_count > 0 else 0
            ci_enlarged_rate = (ci_enlarged_count / total_count) * 100 if total_count > 0 else 0
 
            logging.info(f"  {param} ORIGINAL pass rate: {pass_count}/{total_count} ({pass_rate:.1f}%)")
            logging.info(f"  {param} CI bounds rate: {ci_bounds_count}/{total_count} ({ci_bounds_rate:.1f}%)")
            logging.info(f"  {param} CI enlarged rate: {ci_enlarged_count}/{total_count} ({ci_enlarged_rate:.1f}%)")
 
        # Determine output file path - change .rpt to _enhanced_check_info.csv
        output_file = file_path.replace('.rpt', '_enhanced_check_info.csv')
 
        # Log summary of output dataframe
        logging.debug(f"Enhanced output dataframe preview:\n{result_df.head(3)}")
        logging.info(f"Enhanced output columns: {list(result_df.columns)}")
 
        # Save to CSV
        logging.info(f"Saving enhanced output to: {output_file}")
        result_df.to_csv(output_file, index=False)
        logging.info(f"Enhanced output saved successfully")
 
        return output_file
 
    except Exception as e:
        logging.error(f"Error processing {file_path}", exc_info=True)
        return None
 
def create_enhanced_visualization(results, sigma_results, root_path):
    """
    Create enhanced visualization with 3 separate PNG files and DELAY/SLEW grouping
    """
    logging.info("Creating enhanced visualization with parameter separation and grouping labels")
 
    try:
        import matplotlib
        matplotlib.use('Agg')  # Use non-interactive backend
        import matplotlib.pyplot as plt
        from matplotlib.ticker import MaxNLocator
        import numpy as np
 
        # Set style for better aesthetics
        plt.style.use('seaborn-v0_8-whitegrid')
 
        # Color scheme
        param_colors = {
            'Meanshift': '#3498db',    # Soft blue
            'Std': '#9b59b6',          # Purple
            'Skew': '#2ecc71'          # Green
        }
 
        # Set font properties
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
        plt.rcParams['font.size'] = 12
        plt.rcParams['axes.titlesize'] = 16
        plt.rcParams['axes.labelsize'] = 14
 
        # Prepare data for plotting
        corners = sorted(set(corner for (corner, _) in list(results.keys())))
        types = sorted(set(type_name for (_, type_name) in list(results.keys())))
 
        # Enhanced corner labels
        corner_labels = [c.replace('ssgnp_', '').replace('ssgng_', '').replace('_m40c', '') for c in corners]
 
        visualization_files = []
 
        # Create separate visualization for each parameter
        for param in ['Std', 'Meanshift', 'Skew']:
            logging.info(f"Creating enhanced visualization for: {param}")
 
            # Create figure for this parameter
            fig, ax = plt.subplots(figsize=(16, 10))
 
            # Collect data for this parameter across all corners and types
            plot_data = []
            labels = []
            type_groups = []
 
            # Get all combinations of type and corner
            for type_name in types:
                for corner in corners:
                    if (corner, type_name) in results:
                        rate = results[(corner, type_name)].get(param, 0)
                        plot_data.append(rate)
                        labels.append(f"{type_name.upper()}\n{corner.replace('ssgnp_', '').replace('ssgng_', '').replace('_m40c', '')}")
                        type_groups.append(type_name)
 
            if not plot_data:
                logging.warning(f"No data found for parameter {param}")
                continue
 
            # Create bar chart
            x = np.arange(len(labels))
            width = 0.7
 
            # Create bars with color coding
            colors = ['green' if rate >= 95 else 'orange' if rate >= 90 else 'red' for rate in plot_data]
            bars = ax.bar(x, plot_data, width, color=param_colors[param], alpha=0.8,
                         edgecolor='black', linewidth=1)
 
            # Add value labels on bars
            for bar, rate in zip(bars, plot_data):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                        f'{rate:.1f}%', ha='center', va='bottom',
                        fontweight='bold', fontsize=11)
 
            # Add type separators and background colors
            current_type = None
            type_start = 0
            for i, group_type in enumerate(type_groups):
                if current_type != group_type:
                    if current_type is not None:
                        # Add background color for previous type group
                        if types.index(current_type) % 2 == 0:
                            ax.axvspan(type_start - 0.5, i - 0.5, alpha=0.05, color='blue', zorder=0)
                        # Add vertical separator
                        ax.axvline(x=i - 0.5, color='black', linestyle='-', alpha=0.3, linewidth=2)
                    current_type = group_type
                    type_start = i
 
            # Add background for last type group
            if current_type and types.index(current_type) % 2 == 0:
                ax.axvspan(type_start - 0.5, len(labels) - 0.5, alpha=0.05, color='blue', zorder=0)
 
            # Add horizontal line at the pass threshold
            ax.axhline(y=95, linestyle='--', color='red', alpha=0.8, linewidth=2)
            ax.text(len(labels) * 0.02, 96.5, 'Pass Threshold: 95%', ha='left', va='bottom',
                   fontsize=12, fontweight='bold', color='red',
                   bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.9))
 
            # Add type labels at the top (like sigma visualization)
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
 
            # Add type labels with background (like sigma)
            for pos, name in zip(type_positions, type_names):
                ax.text(pos, max(plot_data) + 7, name, ha='center', va='center',
                       fontweight='bold', fontsize=14, color='navy',
                       bbox=dict(boxstyle="round,pad=0.5", facecolor='lightblue', alpha=0.8))
 
            # Set title and labels
            ax.set_title(f'{param} Pass Rates by Corner and Type\n' +
                        f'Grouped by Type â†’ Corner | Target: 95% Pass Rate',
                        pad=30, fontweight='bold', fontsize=18)
            ax.set_ylabel('Pass Rate (%)', fontweight='bold')
            ax.set_ylim(85, max(plot_data) + 15)  # Give space for type labels
 
            # Set x-axis labels
            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=11)
 
            # Ensure only integer y-ticks
            ax.yaxis.set_major_locator(MaxNLocator(integer=True))
 
            # Add gridlines for better readability
            ax.grid(True, axis='y', linestyle='--', alpha=0.4)
            ax.set_axisbelow(True)
 
            # Set background color
            ax.set_facecolor('#f9f9f9')
 
            # Adjust layout
            plt.tight_layout()
 
            # Save individual parameter visualization
            param_vis_file = os.path.join(root_path, f"moments_{param.lower()}_analysis.png")
            plt.savefig(param_vis_file, dpi=300, bbox_inches='tight', facecolor='white')
            logging.info(f"Enhanced {param} visualization saved to: {param_vis_file}")
            visualization_files.append(param_vis_file)
 
            plt.close(fig)
 
        return visualization_files
 
    except ImportError as e:
        logging.error(f"Could not create visualization: {str(e)}")
        logging.info("Please install matplotlib to enable visualizations")
        return None
    except Exception as e:
        logging.error(f"Error creating enhanced visualization", exc_info=True)
        return None
 
def read_sigma_pr_table(root_path):
    """
    Read the sigma PR table from the root path
 
    Args:
        root_path: Root directory where sigma_PR_table.csv is stored
 
    Returns:
        dict: Dictionary with (corner, type) keys and sigma PR dictionaries as values
    """
    logging.info("Reading sigma PR table")
    sigma_file = os.path.join(root_path, "sigma_PR_table.csv")
 
    if not os.path.exists(sigma_file):
        logging.warning(f"Sigma PR table file not found: {sigma_file}")
        return {}
 
    sigma_pr = {}
 
    try:
        sigma_df = pd.read_csv(sigma_file)
        logging.info(f"Sigma PR table loaded successfully. Shape: {sigma_df.shape}")
 
        # Debug the columns
        logging.debug(f"Sigma table columns: {list(sigma_df.columns)}")
 
        # Check if the required columns exist
        if 'Corner' not in sigma_df.columns or 'Type' not in sigma_df.columns:
            logging.error("Sigma PR table must have 'Corner' and 'Type' columns")
            return {}
 
        if 'early_sigma' not in sigma_df.columns or 'late_sigma' not in sigma_df.columns:
            logging.error("Sigma PR table must have 'early_sigma' and 'late_sigma' columns")
            return {}
 
        # Create a dictionary to store the sigma PR values
        for _, row in sigma_df.iterrows():
            corner = row['Corner']
            type_name = row['Type']
            early_sigma = row['early_sigma']
            late_sigma = row['late_sigma']
 
            # Convert to float if stored as string with % symbol
            if isinstance(early_sigma, str) and '%' in early_sigma:
                early_sigma = float(early_sigma.strip('%'))
            if isinstance(late_sigma, str) and '%' in late_sigma:
                late_sigma = float(late_sigma.strip('%'))
 
            sigma_pr[(corner, type_name)] = {
                'early_sigma': early_sigma,
                'late_sigma': late_sigma
            }
 
        logging.info(f"Loaded sigma PR values for {len(sigma_pr)} corner-type combinations")
 
    except Exception as e:
        logging.error(f"Error reading sigma PR table", exc_info=True)
 
    return sigma_pr
 
def generate_enhanced_summary_table(results, sigma_results, root_path):
    """
    Generate enhanced summary table with 1-digit precision
 
    Args:
        results: Dictionary with (corner, type) keys and pass rate dictionaries as values
        sigma_results: Dictionary with (corner, type) keys and sigma PR dictionaries as values
        root_path: Root directory path to save the summary file
 
    Returns:
        tuple: (summary_file_path, csv_file_path)
    """
    logging.info("Generating enhanced combined summary table")
 
    # Create dataframes for each type
    delay_df = pd.DataFrame(columns=[
        'Corner',
        'early_sigma PR', 'early_sigma Status',
        'late_sigma PR', 'late_sigma Status',
        'Meanshift PR', 'Meanshift Status',
        'Std PR', 'Std Status',
        'Skew PR', 'Skew Status'
    ])
 
    slew_df = pd.DataFrame(columns=[
        'Corner',
        'early_sigma PR', 'early_sigma Status',
        'late_sigma PR', 'late_sigma Status',
        'Meanshift PR', 'Meanshift Status',
        'Std PR', 'Std Status',
        'Skew PR', 'Skew Status'
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
 
    for (corner, type_name) in sigma_results.keys():
        all_corners.add(corner)
        all_types.add(type_name)
 
    for corner in sorted(all_corners):
        for type_name in sorted(all_types):
            # Start with an empty row
            new_row = {'Corner': corner}
 
            # Add standard results
            if (corner, type_name) in results:
                rates = results[(corner, type_name)]
                for param in ['Meanshift', 'Std', 'Skew']:
                    rate = rates.get(param, 0)
                    new_row[f'{param} PR'] = rate
                    new_row[f'{param} Status'] = 'Pass' if rate >= pass_threshold else 'Fail'
            else:
                for param in ['Meanshift', 'Std', 'Skew']:
                    new_row[f'{param} PR'] = 0
                    new_row[f'{param} Status'] = 'N/A'
 
            # Add sigma results
            if (corner, type_name) in sigma_results:
                sigma_rates = sigma_results[(corner, type_name)]
                for param in ['early_sigma', 'late_sigma']:
                    rate = sigma_rates.get(param, 0)
                    new_row[f'{param} PR'] = rate
                    new_row[f'{param} Status'] = 'Pass' if rate >= pass_threshold else 'Fail'
            else:
                for param in ['early_sigma', 'late_sigma']:
                    new_row[f'{param} PR'] = 0
                    new_row[f'{param} Status'] = 'N/A'
 
            # Add to the appropriate dataframe
            if type_name == 'delay':
                delay_df = pd.concat([delay_df, pd.DataFrame([new_row])], ignore_index=True)
            else:  # slew
                slew_df = pd.concat([slew_df, pd.DataFrame([new_row])], ignore_index=True)
 
    # Format for better display with 1-digit precision
    for df in [delay_df, slew_df]:
        for param in ['early_sigma', 'late_sigma', 'Meanshift', 'Std', 'Skew']:
            df[f'{param} PR'] = df[f'{param} PR'].map('{:.1f}%'.format)
 
    # Create the summary string
    summary = "Enhanced Combined Summary Table (1-digit precision)\n"
    summary += "\nDelay:\n"
    summary += delay_df.to_string(index=False)
    summary += "\n\nSlew:\n"
    summary += slew_df.to_string(index=False)
 
    # Save to file
    summary_file = os.path.join(root_path, "enhanced_combined_summary_table.txt")
    with open(summary_file, 'w') as f:
        f.write(summary)
 
    logging.info(f"Enhanced combined summary table saved to: {summary_file}")
 
    # Also create a CSV version for easier processing
    csv_file = os.path.join(root_path, "enhanced_combined_summary_table.csv")
 
    # Combine dataframes with a Type column
    delay_df['Type'] = 'delay'
    slew_df['Type'] = 'slew'
    combined_df = pd.concat([delay_df, slew_df], ignore_index=True)
 
    # Save to CSV
    combined_df.to_csv(csv_file, index=False)
    logging.info(f"Enhanced combined summary CSV saved to: {csv_file}")
 
    return summary_file, csv_file
 
def main():
    # Set up a main log file
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    main_log_file = f"enhanced_moments_check_{timestamp}.log"
 
    # Configure main logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(main_log_file),
            logging.StreamHandler()
        ]
    )
 
    logging.info("="*80)
    logging.info("Starting ENHANCED moments check script (ORIGINAL LOGIC PRESERVED)")
    logging.info(f"Main log file: {main_log_file}")
    logging.info("NEW FEATURES: 3 separate PNG files, DELAY/SLEW grouping, additional criteria comparison")
    logging.info("="*80)
 
    # Get parameters from environment variables
    root_path = os.environ.get('combined_data_root_path')
    corners_str = os.environ.get('corners')
    types_str = os.environ.get('types')
 
    logging.info("Reading parameters:")
 
    # Parse corners and types
    if corners_str and (corners_str.startswith('(') or corners_str.startswith('[')):
        # Handle different array/tuple formats from shell
        corners = corners_str.strip('()[]').replace('"', '').replace("'", '').split()
        logging.info(f"  Corners from environment: {corners}")
    else:
        corners = ["ssgnp_0p450v_m40c", "ssgnp_0p465v_m40c", "ssgnp_0p480v_m40c", "ssgnp_0p495v_m40c"]
        logging.info(f"  Using default corners: {corners}")
 
    if types_str and (types_str.startswith('(') or types_str.startswith('[')):
        types = types_str.strip('()[]').replace('"', '').replace("'", '').split()
        logging.info(f"  Types from environment: {types}")
    else:
        types = ["delay", "slew"]
        logging.info(f"  Using default types: {types}")
 
    if not root_path:
        root_path = "/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2024/N2P/5-moments_results/1-CDNS/R1"
        logging.info(f"  Using default root path: {root_path}")
    else:
        logging.info(f"  Root path from environment: {root_path}")
 
    # Check if root path exists
    if not os.path.exists(root_path):
        logging.error(f"Root path does not exist: {root_path}")
        return
 
    # Find matching RPT files
    rpt_files = find_rpt_files(root_path, corners, types)
 
    if not rpt_files:
        logging.error("No matching RPT files found!")
        return
 
    # Process each found file
    successful_files = []
    failed_files = []
 
    # Dictionary to store pass rates for summary table
    pass_rates = {}
 
    for (corner, type_name), file_path in rpt_files.items():
        logging.info(f"Processing enhanced {corner} - {type_name}: {file_path}")
        result = process_file(file_path, type_name)
 
        if result:
            successful_files.append(file_path)
 
            # Calculate pass rates for this file
            try:
                output_df = pd.read_csv(result)
                file_rates = {}
 
                for param in ['Meanshift', 'Std', 'Skew']:
                    passes = (output_df[param] == 'Pass').sum()
                    total = len(output_df)
                    rate = (passes / total) * 100 if total > 0 else 0
                    file_rates[param] = rate
                    logging.info(f"  {param} pass rate: {passes}/{total} ({rate:.1f}%)")
 
                # Store rates for summary table
                pass_rates[(corner, type_name)] = file_rates
 
            except Exception as e:
                logging.error(f"Error calculating pass rates for {file_path}", exc_info=True)
        else:
            failed_files.append(file_path)
 
    # Read sigma PR table
    sigma_results = read_sigma_pr_table(root_path)
 
    # Log summary
    logging.info("="*80)
    logging.info("Enhanced processing summary:")
    logging.info(f"  Total files found: {len(rpt_files)}")
    logging.info(f"  Successfully processed: {len(successful_files)}")
    logging.info(f"  Failed to process: {len(failed_files)}")
 
    if failed_files:
        logging.info("Failed files:")
        for file in failed_files:
            logging.info(f"    {file}")
 
    # Generate enhanced summary table and visualization
    if pass_rates:
        logging.info("Generating enhanced summary and visualization")
 
        # Generate enhanced visualization with 3 separate PNG files
        vis_files = create_enhanced_visualization(pass_rates, sigma_results, root_path)
        if vis_files:
            logging.info("Enhanced visualizations saved:")
            for vis_file in vis_files:
                logging.info(f"  - {vis_file}")
 
        # Generate enhanced summary tables
        summary_file, csv_file = generate_enhanced_summary_table(pass_rates, sigma_results, root_path)
 
        logging.info(f"Enhanced combined summary table saved to: {summary_file}")
        logging.info(f"Enhanced combined summary CSV saved to: {csv_file}")
 
        # Print summary to console
        with open(summary_file, 'r') as f:
            summary_content = f.read()
        print('\n' + "="*50)
        print("ENHANCED COMBINED SUMMARY TABLE:")
        print(f"="*50)
        print(summary_content)
        print("="*50)
        print("ENHANCEMENTS ADDED:")
        print("   3 separate PNG files (Std, Meanshift, Skew)")
        print("   DELAY/SLEW grouping labels like sigma visualization")
        print("   Additional criteria comparison (CI bounds + enlargement)")
        print("   1-digit precision throughout")
        print("   Enhanced corner extraction")
        print("   Pass reason tracking")
        print("   ORIGINAL PASS/FAIL LOGIC PRESERVED")
        print("="*50)
    else:
        logging.warning("Could not generate enhanced summary table - no valid results")
 
    logging.info("="*80)
    logging.info("Enhanced moments script completed with ORIGINAL LOGIC PRESERVED")
 
if __name__ == "__main__":
    main()
