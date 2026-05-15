#!/usr/bin/env python3
"""
CI Validation Python Script - Complete Version
This script validates CSV files in the specified data path with comprehensive cross-corner analysis
File naming pattern: fmc_*_{corner}_{type}.csv
 
Features:
- Converts sigma data back to percentile data for validation (original simulation output)
- Validates CI ranges on percentile data for delay/slew and hold/mpw with different criteria
- Detailed calculation processes for each validation showing sigma-to-percentile conversion
- Cross-corner analysis to find arcs validated across all corners
- Delay & slew overlap analysis
- Comprehensive reporting with summary tables
- Organized output in separate subdirectories
 
Validation Approach:
- Input: Sigma data from CSV files (post-processed from simulation percentile data)
- Process: Convert sigma back to percentile data using provided formulas
- Validate: Apply CI validation criteria to percentile ranges
- Output: Pass/fail results with detailed calculation traces
"""
 
import argparse
import os
import sys
import pandas as pd
import glob
from datetime import datetime
import logging
import numpy as np
 
class CIValidator:
    def __init__(self, data_path, types, corners, log_file):
        self.data_path = data_path
        self.types = types
        self.corners = corners
        self.log_file = log_file
        self.validation_results = []
        self.summary_stats = {}
        self.validated_arcs_by_type_corner = {}  # Track validated arcs by type and corner
       
        # Setup logging
        self.setup_logging()
       
        # Create output subdirectories
        self.create_output_directories()
       
    def create_output_directories(self):
        """Create subdirectories for organizing output files"""
        self.validated_dir = os.path.join(self.data_path, "validated")
        self.failed_dir = os.path.join(self.data_path, "failed")
        self.analysis_dir = os.path.join(self.data_path, "cross_corner_analysis")
       
        try:
            os.makedirs(self.validated_dir, exist_ok=True)
            os.makedirs(self.failed_dir, exist_ok=True)
            os.makedirs(self.analysis_dir, exist_ok=True)
            self.logger.info(f"Created output directories:")
            self.logger.info(f"  Validated files: {self.validated_dir}")
            self.logger.info(f"  Failed files: {self.failed_dir}")
            self.logger.info(f"  Cross-corner analysis: {self.analysis_dir}")
        except Exception as e:
            self.logger.error(f"Error creating output directories: {str(e)}")
           
    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file, mode='a'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
       
    def find_csv_files(self):
        """Find all CSV files matching the pattern fmc_*_{corner}_{type}.csv"""
        csv_files = {}
       
        self.logger.info("Searching for CSV files...")
       
        for corner in self.corners:
            csv_files[corner] = {}
            for type_name in self.types:
                # Pattern: fmc_*_{corner}_{type}.csv
                pattern = os.path.join(self.data_path, f"fmc_*_{corner}_{type_name}.csv")
                matching_files = glob.glob(pattern)
               
                if matching_files:
                    csv_files[corner][type_name] = matching_files
                    self.logger.info(f"Found {len(matching_files)} file(s) for {corner}-{type_name}")
                    for file in matching_files:
                        self.logger.info(f"  - {os.path.basename(file)}")
                else:
                    self.logger.warning(f"No files found for pattern: {pattern}")
                    csv_files[corner][type_name] = []
       
        return csv_files
   
    def validate_file_existence(self, csv_files):
        """Validate that expected files exist"""
        self.logger.info("\n" + "="*50)
        self.logger.info("VALIDATING FILE EXISTENCE")
        self.logger.info("="*50)
       
        missing_files = []
        total_expected = len(self.corners) * len(self.types)
        total_found = 0
       
        for corner in self.corners:
            for type_name in self.types:
                files = csv_files.get(corner, {}).get(type_name, [])
                if files:
                    total_found += len(files)
                else:
                    missing_files.append(f"{corner}-{type_name}")
       
        if missing_files:
            self.logger.error(f"Missing files for: {', '.join(missing_files)}")
            return False
        else:
            self.logger.info(f"All expected file patterns found! Total files: {total_found}")
            return True
   
    def validate_headers(self, df, type_name):
        """Validate CSV headers based on type"""
        # Define expected headers for each type
        expected_headers = {
            'delay': ['Arc', 'Cell_Name', 'MC_Nominal', 'MC_Early_Sigma', 'MC_Early_Sigma_UB',
                     'MC_Early_Sigma_LB', 'MC_Late_Sigma', 'MC_Late_Sigma_UB', 'MC_Late_Sigma_LB', 'Table_Type'],
            'slew': ['Arc', 'Cell_Name', 'MC_Nominal', 'MC_Early_Sigma', 'MC_Early_Sigma_UB',
                    'MC_Early_Sigma_LB', 'MC_Late_Sigma', 'MC_Late_Sigma_UB', 'MC_Late_Sigma_LB', 'Table_Type'],
            'hold': ['Arc', 'Cell_Name', 'MC_Nominal', 'MC_Late_Sigma', 'MC_Late_Sigma_UB', 'MC_Late_Sigma_LB', 'Table_Type'],
            'mpw': ['Arc', 'Cell_Name', 'MC_Nominal', 'MC_Late_Sigma', 'MC_Late_Sigma_UB', 'MC_Late_Sigma_LB', 'Table_Type']
        }
       
        if type_name in expected_headers:
            required_headers = expected_headers[type_name]
            missing_headers = set(required_headers) - set(df.columns)
            if missing_headers:
                self.logger.error(f"  Missing required headers: {missing_headers}")
                return False
            self.logger.info(f"  All required headers present for {type_name}")
       
        return True
   
    def validate_ci_row_delay_slew(self, row, type_name):
        """Validate CI for delay/slew type rows with detailed calculation process - using percentile data"""
        try:
            # Get thresholds based on type
            if type_name == 'delay':
                percentage_threshold = 0.04  # 4%
                absolute_threshold = 2       # 2ps
            else:  # slew
                percentage_threshold = 0.08  # 8%
                absolute_threshold = 4       # 4ps
           
            nominal = row['MC_Nominal']
           
            # Skip if nominal is too close to zero
            if abs(nominal) < 1e-12:
                return False, "MC_Nominal value too close to zero", "MC_Nominal value too close to zero"
           
            # Convert sigma data back to percentile data
            # Early percentile conversion: mc_early_sigma = (mc_nominal - mc_per)/3
            # So: mc_per = mc_nominal - 3 * mc_early_sigma
            early_sigma_ub = row['MC_Early_Sigma_UB']
            early_sigma_lb = row['MC_Early_Sigma_LB']
            early_per_ub = nominal - 3 * early_sigma_ub
            early_per_lb = nominal - 3 * early_sigma_lb
            early_per_range = abs(early_per_ub - early_per_lb)
           
            # Late percentile conversion: mc_late_sigma = (mc_per - mc_nominal)/3 
            # So: mc_per = mc_nominal + 3 * mc_late_sigma
            late_sigma_ub = row['MC_Late_Sigma_UB']
            late_sigma_lb = row['MC_Late_Sigma_LB']
            late_per_ub = nominal + 3 * late_sigma_ub
            late_per_lb = nominal + 3 * late_sigma_lb
            late_per_range = abs(late_per_ub - late_per_lb)
           
            # Validate Early Percentile Range
            early_condition1 = early_per_range / abs(nominal) <= percentage_threshold
            early_condition2 = early_per_range <= absolute_threshold
            early_pass = early_condition1 or early_condition2
           
            # Validate Late Percentile Range
            late_condition1 = late_per_range / abs(nominal) <= percentage_threshold
            late_condition2 = late_per_range <= absolute_threshold
            late_pass = late_condition1 or late_condition2
           
            # Row passes if both early and late pass
            overall_pass = early_pass and late_pass
           
            # Detailed calculation process
            calc_details = []
            calc_details.append(f"=== {type_name.upper()} VALIDATION CALCULATION ===")
            calc_details.append(f"MC_Nominal = {nominal}")
            calc_details.append(f"Thresholds: {percentage_threshold*100}% or {absolute_threshold}ps")
            calc_details.append("")
           
            calc_details.append("EARLY PERCENTILE CONVERSION:")
            calc_details.append(f"  MC_Early_Sigma_UB = {early_sigma_ub}")
            calc_details.append(f"  MC_Early_Sigma_LB = {early_sigma_lb}")
            calc_details.append(f"  MC_Per_UB (early) = {nominal} - 3 * {early_sigma_ub} = {early_per_ub}")
            calc_details.append(f"  MC_Per_LB (early) = {nominal} - 3 * {early_sigma_lb} = {early_per_lb}")
            calc_details.append(f"  Early_per_range = |{early_per_ub} - {early_per_lb}| = {early_per_range}")
            calc_details.append(f"  Condition 1: {early_per_range}/{abs(nominal)} = {early_per_range/abs(nominal):.6f} <= {percentage_threshold} ? {early_condition1}")
            calc_details.append(f"  Condition 2: {early_per_range} <= {absolute_threshold} ? {early_condition2}")
            calc_details.append(f"  Early PASS: {early_pass} (Condition 1 OR Condition 2)")
            calc_details.append("")
           
            calc_details.append("LATE PERCENTILE CONVERSION:")
            calc_details.append(f"  MC_Late_Sigma_UB = {late_sigma_ub}")
            calc_details.append(f"  MC_Late_Sigma_LB = {late_sigma_lb}")
            calc_details.append(f"  MC_Per_UB (late) = {nominal} + 3 * {late_sigma_ub} = {late_per_ub}")
            calc_details.append(f"  MC_Per_LB (late) = {nominal} + 3 * {late_sigma_lb} = {late_per_lb}")
            calc_details.append(f"  Late_per_range = |{late_per_ub} - {late_per_lb}| = {late_per_range}")
            calc_details.append(f"  Condition 1: {late_per_range}/{abs(nominal)} = {late_per_range/abs(nominal):.6f} <= {percentage_threshold} ? {late_condition1}")
            calc_details.append(f"  Condition 2: {late_per_range} <= {absolute_threshold} ? {late_condition2}")
            calc_details.append(f"  Late PASS: {late_pass} (Condition 1 OR Condition 2)")
            calc_details.append("")
            calc_details.append(f"OVERALL RESULT: {overall_pass} (Early PASS AND Late PASS)")
           
            # Summary for CSV
            summary = f"Early_per: range={early_per_range:.3f}, %={early_per_range/abs(nominal)*100:.2f}%, pass={early_pass} | " + \
                     f"Late_per: range={late_per_range:.3f}, %={late_per_range/abs(nominal)*100:.2f}%, pass={late_pass} | Overall: {overall_pass}"
           
            detailed_calc = " | ".join(calc_details)
           
            return overall_pass, summary, detailed_calc
           
        except Exception as e:
            return False, f"Error in validation: {str(e)}", f"Calculation error: {str(e)}"
   
    def validate_ci_row_hold_mpw(self, row, type_name):
        """Validate CI for hold/mpw type rows with detailed calculation process - using percentile data"""
        try:
            # Convert sigma data back to percentile data
            # Late percentile conversion: mc_late_sigma = (mc_per - mc_nominal)/3
            # So: mc_per = mc_nominal + 3 * mc_late_sigma
            nominal = row['MC_Nominal']  # Use MC_Nominal as nominal for hold/mpw
            late_sigma_ub = row['MC_Late_Sigma_UB']
            late_sigma_lb = row['MC_Late_Sigma_LB']
           
            ci_per_ub = nominal + 3 * late_sigma_ub
            ci_per_lb = nominal + 3 * late_sigma_lb
            ci_per_range = abs(ci_per_ub - ci_per_lb)
            ci_per_middle = (ci_per_ub + ci_per_lb) / 2  # Middle of percentile values
           
            # Detailed calculation process
            calc_details = []
            calc_details.append(f"=== {type_name.upper()} VALIDATION CALCULATION ===")
            calc_details.append(f"MC_Nominal = {nominal}")
            calc_details.append(f"MC_Late_Sigma_UB = {late_sigma_ub}")
            calc_details.append(f"MC_Late_Sigma_LB = {late_sigma_lb}")
            calc_details.append("")
           
            calc_details.append("PERCENTILE CONVERSION:")
            calc_details.append(f"  CI_Per_UB = {nominal} + 3 * {late_sigma_ub} = {ci_per_ub}")
            calc_details.append(f"  CI_Per_LB = {nominal} + 3 * {late_sigma_lb} = {ci_per_lb}")
            calc_details.append(f"  CI_per_range = |{ci_per_ub} - {ci_per_lb}| = {ci_per_range}")
            calc_details.append(f"  CI_per_middle = ({ci_per_ub} + {ci_per_lb}) / 2 = {ci_per_middle}")
            calc_details.append("")
           
            # Condition 3: CI range <= 10ps (check first for efficiency)
            condition3 = ci_per_range <= 10
            calc_details.append(f"CONDITION 3: CI_per_range <= 10ps")
            calc_details.append(f"  {ci_per_range} <= 10 ? {condition3}")
           
            if condition3:
                calc_details.append(f"RESULT: PASS (Condition 3 satisfied)")
                summary = f"CI_per_range={ci_per_range:.3f}ps <= 10ps â†’ PASS"
                detailed_calc = " | ".join(calc_details)
                return True, summary, detailed_calc
           
            calc_details.append("")
           
            # Check conditions 1 and 2
            # Condition 1: |(CI_Per_UB - nominal) / (CI_Per_LB - nominal)| <= 1.15
            denominator1 = ci_per_lb - nominal
            if abs(denominator1) < 1e-12:
                calc_details.append(f"CONDITION 1: |(CI_Per_UB - nominal) / (CI_Per_LB - nominal)| <= 1.15")
                calc_details.append(f"  Denominator (CI_Per_LB - nominal) = {ci_per_lb} - {nominal} = {denominator1}")
                calc_details.append(f"  ERROR: Denominator too close to zero")
                calc_details.append(f"RESULT: FAIL (Cannot calculate condition 1)")
                summary = "CI_Per_LB - MC_Nominal too close to zero"
                detailed_calc = " | ".join(calc_details)
                return False, summary, detailed_calc
           
            ratio1 = abs((ci_per_ub - nominal) / denominator1)
            condition1 = ratio1 <= 1.15
           
            calc_details.append(f"CONDITION 1: |(CI_Per_UB - nominal) / (CI_Per_LB - nominal)| <= 1.15")
            calc_details.append(f"  Numerator = CI_Per_UB - nominal = {ci_per_ub} - {nominal} = {ci_per_ub - nominal}")
            calc_details.append(f"  Denominator = CI_Per_LB - nominal = {ci_per_lb} - {nominal} = {denominator1}")
            calc_details.append(f"  Ratio = |{ci_per_ub - nominal} / {denominator1}| = {ratio1:.6f}")
            calc_details.append(f"  {ratio1:.6f} <= 1.15 ? {condition1}")
            calc_details.append("")
           
            # Condition 2: CI_per_range / |CI_Per_Middle - nominal| <= 1.035
            denominator2 = ci_per_middle - nominal
            if abs(denominator2) < 1e-12:
                calc_details.append(f"CONDITION 2: CI_per_range / |CI_per_middle - nominal| <= 1.035")
                calc_details.append(f"  Denominator (CI_per_middle - nominal) = {ci_per_middle} - {nominal} = {denominator2}")
                calc_details.append(f"  ERROR: Denominator too close to zero")
                calc_details.append(f"RESULT: FAIL (Cannot calculate condition 2)")
                summary = "CI_per_middle - MC_Nominal too close to zero"
                detailed_calc = " | ".join(calc_details)
                return False, summary, detailed_calc
           
            ratio2 = ci_per_range / abs(denominator2)
            condition2 = ratio2 <= 1.035
           
            calc_details.append(f"CONDITION 2: CI_per_range / |CI_per_middle - nominal| <= 1.035")
            calc_details.append(f"  Numerator = CI_per_range = {ci_per_range}")
            calc_details.append(f"  Denominator = |CI_per_middle - nominal| = |{ci_per_middle} - {nominal}| = {abs(denominator2)}")
            calc_details.append(f"  Ratio = {ci_per_range} / {abs(denominator2)} = {ratio2:.6f}")
            calc_details.append(f"  {ratio2:.6f} <= 1.035 ? {condition2}")
            calc_details.append("")
           
            # Pass if (condition1 AND condition2) OR condition3
            overall_pass = (condition1 and condition2) or condition3
           
            calc_details.append(f"FINAL EVALUATION:")
            calc_details.append(f"  Condition 1: {condition1}")
            calc_details.append(f"  Condition 2: {condition2}")
            calc_details.append(f"  Condition 3: {condition3}")
            calc_details.append(f"  (Condition 1 AND Condition 2) = {condition1 and condition2}")
            calc_details.append(f"  OVERALL: ({condition1 and condition2}) OR {condition3} = {overall_pass}")
           
            summary = f"CI_per_range={ci_per_range:.3f}, ratio1={ratio1:.3f}<=1.15?{condition1}, " + \
                     f"ratio2={ratio2:.3f}<=1.035?{condition2}, range<=10?{condition3} â†’ {'PASS' if overall_pass else 'FAIL'}"
           
            detailed_calc = " | ".join(calc_details)
           
            return overall_pass, summary, detailed_calc
           
        except Exception as e:
            return False, f"Error in validation: {str(e)}", f"Calculation error: {str(e)}"
   
    def validate_data_types(self, df, type_name):
        """Validate data types in CSV"""
        numeric_columns = ['MC_Nominal', 'MC_Late_Sigma', 'MC_Late_Sigma_UB', 'MC_Late_Sigma_LB']
       
        if type_name in ['delay', 'slew']:
            numeric_columns.extend(['MC_Early_Sigma', 'MC_Early_Sigma_UB', 'MC_Early_Sigma_LB'])
       
        for col in numeric_columns:
            if col in df.columns:
                try:
                    pd.to_numeric(df[col], errors='raise')
                except:
                    self.logger.error(f"  Column {col} contains non-numeric values")
                    return False
       
        return True
   
    def process_csv_file(self, file_path, corner, type_name):
        """Process a single CSV file and generate validated/failed output files"""
        try:
            self.logger.info(f"\nProcessing: {os.path.basename(file_path)}")
           
            # Read CSV file
            df = pd.read_csv(file_path)
           
            if df.empty:
                self.logger.warning(f"  File is empty, skipping")
                return True
           
            # Convert numeric columns
            numeric_columns = ['MC_Nominal', 'MC_Late_Sigma', 'MC_Late_Sigma_UB', 'MC_Late_Sigma_LB']
            if type_name in ['delay', 'slew']:
                numeric_columns.extend(['MC_Early_Sigma', 'MC_Early_Sigma_UB', 'MC_Early_Sigma_LB'])
           
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
           
            # Add validation result columns
            df['Validation_Result'] = ''
            df['Validation_Summary'] = ''
            df['Validation_Detailed_Calculation'] = ''
           
            # Apply validation to each row
            validated_rows = []
            failed_rows = []
           
            for idx, row in df.iterrows():
                if type_name in ['delay', 'slew']:
                    is_valid, summary, detailed_calc = self.validate_ci_row_delay_slew(row, type_name)
                else:  # hold, mpw
                    is_valid, summary, detailed_calc = self.validate_ci_row_hold_mpw(row, type_name)
               
                # Update validation columns
                df.at[idx, 'Validation_Result'] = 'PASS' if is_valid else 'FAIL'
                df.at[idx, 'Validation_Summary'] = summary
                df.at[idx, 'Validation_Detailed_Calculation'] = detailed_calc
               
                if is_valid:
                    validated_rows.append(idx)
                else:
                    failed_rows.append(idx)
           
            # Create output DataFrames
            validated_df = df.loc[validated_rows].copy()
            failed_df = df.loc[failed_rows].copy()
           
            # Generate output file names and save to subdirectories
            base_name = os.path.splitext(os.path.basename(file_path))[0]
           
            validated_file = os.path.join(self.validated_dir, f"{base_name}_VALIDATED.csv")
            failed_file = os.path.join(self.failed_dir, f"{base_name}_FAILED.csv")
           
            # Save output files
            if not validated_df.empty:
                validated_df.to_csv(validated_file, index=False)
                self.logger.info(f"  Saved {len(validated_df)} validated rows to: validated/{os.path.basename(validated_file)}")
           
            if not failed_df.empty:
                failed_df.to_csv(failed_file, index=False)
                self.logger.info(f"  Saved {len(failed_df)} failed rows to: failed/{os.path.basename(failed_file)}")
           
            # Log statistics
            total_rows = len(df)
            validated_count = len(validated_df)
            failed_count = len(failed_df)
           
            self.logger.info(f"  Statistics: Total={total_rows}, Validated={validated_count} ({validated_count/total_rows*100:.1f}%), Failed={failed_count} ({failed_count/total_rows*100:.1f}%)")
           
            # Log some example calculations for verification
            if total_rows > 0:
                self.logger.info(f"  Example calculations (first 2 rows):")
                for i, (idx, row) in enumerate(df.head(2).iterrows()):
                    result = row['Validation_Result']
                    summary = row['Validation_Summary']
                    self.logger.info(f"    Row {idx+1}: {result} - {summary}")
                    if i >= 1:  # Only show first 2 examples
                        break
           
            # Store statistics for summary table
            key = f"{corner}_{type_name}"
            if key not in self.summary_stats:
                self.summary_stats[key] = {
                    'corner': corner,
                    'type': type_name,
                    'total_files': 0,
                    'total_rows': 0,
                    'validated_rows': 0,
                    'failed_rows': 0
                }
           
            self.summary_stats[key]['total_files'] += 1
            self.summary_stats[key]['total_rows'] += total_rows
            self.summary_stats[key]['validated_rows'] += validated_count
            self.summary_stats[key]['failed_rows'] += failed_count
           
            # Track validated arcs for cross-corner analysis
            if not validated_df.empty and 'Arc' in validated_df.columns:
                type_corner_key = f"{type_name}_{corner}"
                validated_arcs = set(validated_df['Arc'].unique())
               
                if type_corner_key not in self.validated_arcs_by_type_corner:
                    self.validated_arcs_by_type_corner[type_corner_key] = set()
               
                self.validated_arcs_by_type_corner[type_corner_key].update(validated_arcs)
               
                self.logger.info(f"  Tracked {len(validated_arcs)} unique validated arcs for {type_name}-{corner}")
           
            return True
           
        except Exception as e:
            self.logger.error(f"  Error processing {file_path}: {str(e)}")
            return False
   
    def validate_csv_structure_and_process(self, csv_files):
        """Validate CSV file structure and process files"""
        self.logger.info("\n" + "="*50)
        self.logger.info("VALIDATING CSV STRUCTURE AND PROCESSING FILES")
        self.logger.info("="*50)
       
        validation_passed = True
        processed_files = 0
        total_validated_rows = 0
        total_failed_rows = 0
       
        for corner in self.corners:
            for type_name in self.types:
                files = csv_files.get(corner, {}).get(type_name, [])
               
                for file_path in files:
                    try:
                        self.logger.info(f"\nValidating structure: {os.path.basename(file_path)}")
                       
                        # Read CSV file for structure validation
                        df = pd.read_csv(file_path)
                       
                        # Basic validations
                        if df.empty:
                            self.logger.error(f"  ERROR: File is empty")
                            validation_passed = False
                            continue
                       
                        # Log basic info
                        self.logger.info(f"  Rows: {len(df)}, Columns: {len(df.columns)}")
                        self.logger.info(f"  Headers: {list(df.columns)}")
                       
                        # Validate headers
                        if not self.validate_headers(df, type_name):
                            validation_passed = False
                            continue
                       
                        # Validate data types
                        if not self.validate_data_types(df, type_name):
                            validation_passed = False
                            continue
                       
                        # Process the file (validate CI and generate output files)
                        if self.process_csv_file(file_path, corner, type_name):
                            processed_files += 1
                        else:
                            validation_passed = False
                       
                    except Exception as e:
                        self.logger.error(f"  ERROR processing {file_path}: {str(e)}")
                        validation_passed = False
       
        self.logger.info(f"\nProcessing Summary: {processed_files} files processed successfully")
        return validation_passed
   
    def perform_cross_corner_analysis(self):
        """Perform cross-corner analysis to find arcs validated across all corners"""
        self.logger.info("\n" + "="*80)
        self.logger.info("CROSS-CORNER ANALYSIS")
        self.logger.info("="*80)
       
        cross_corner_results = {}
       
        # Analysis for each type: find arcs validated across ALL corners
        for type_name in self.types:
            self.logger.info(f"\nAnalyzing {type_name.upper()} across all corners...")
           
            # Get validated arcs for this type across all corners
            corner_arc_sets = []
            for corner in self.corners:
                type_corner_key = f"{type_name}_{corner}"
                if type_corner_key in self.validated_arcs_by_type_corner:
                    arcs = self.validated_arcs_by_type_corner[type_corner_key]
                    corner_arc_sets.append(arcs)
                    self.logger.info(f"  {corner}: {len(arcs)} validated arcs")
                else:
                    self.logger.warning(f"  {corner}: No validated arcs found")
                    corner_arc_sets.append(set())
           
            # Find intersection of all corners for this type
            if corner_arc_sets:
                arcs_all_corners = set.intersection(*corner_arc_sets) if corner_arc_sets else set()
                cross_corner_results[type_name] = arcs_all_corners
               
                self.logger.info(f"  RESULT: {len(arcs_all_corners)} arcs validated across ALL corners for {type_name}")
               
                # Generate output file for this type
                if arcs_all_corners:
                    self.generate_cross_corner_output(type_name, arcs_all_corners)
            else:
                cross_corner_results[type_name] = set()
                self.logger.warning(f"  No data available for {type_name}")
       
        # Special analysis: delay & slew overlap
        if 'delay' in cross_corner_results and 'slew' in cross_corner_results:
            self.logger.info(f"\nAnalyzing DELAY & SLEW OVERLAP...")
           
            delay_arcs = cross_corner_results['delay']
            slew_arcs = cross_corner_results['slew']
            delay_slew_overlap = delay_arcs.intersection(slew_arcs)
           
            self.logger.info(f"  Delay arcs (all corners): {len(delay_arcs)}")
            self.logger.info(f"  Slew arcs (all corners): {len(slew_arcs)}")
            self.logger.info(f"  OVERLAP: {len(delay_slew_overlap)} arcs validated in BOTH delay & slew across all corners")
           
            if delay_slew_overlap:
                self.generate_delay_slew_overlap_output(delay_slew_overlap, delay_arcs, slew_arcs)
       
        return cross_corner_results
   
    def generate_cross_corner_output(self, type_name, validated_arcs):
        """Generate output file for arcs validated across all corners for a specific type"""
        try:
            # Collect detailed information for these arcs from validated files
            arc_details = []
           
            for corner in self.corners:
                # Look for validated files for this type and corner
                pattern = os.path.join(self.validated_dir, f"fmc_*_{corner}_{type_name}_VALIDATED.csv")
                matching_files = glob.glob(pattern)
               
                for file_path in matching_files:
                    try:
                        df = pd.read_csv(file_path)
                        if 'Arc' in df.columns:
                            # Filter for arcs that are in our cross-corner validated set
                            filtered_df = df[df['Arc'].isin(validated_arcs)].copy()
                            if not filtered_df.empty:
                                filtered_df['Source_Corner'] = corner
                                filtered_df['Source_File'] = os.path.basename(file_path)
                                arc_details.append(filtered_df)
                    except Exception as e:
                        self.logger.warning(f"  Error reading {file_path}: {str(e)}")
           
            if arc_details:
                # Combine all data
                combined_df = pd.concat(arc_details, ignore_index=True)
               
                # Create summary by arc
                arc_summary = []
                for arc in sorted(validated_arcs):
                    arc_data = combined_df[combined_df['Arc'] == arc]
                    corners_found = sorted(arc_data['Source_Corner'].unique())
                    files_found = sorted(arc_data['Source_File'].unique())
                   
                    arc_summary.append({
                        'Arc': arc,
                        'Validated_Corners': ', '.join(corners_found),
                        'Corners_Count': len(corners_found),
                        'Source_Files': ', '.join(files_found),
                        'Total_Occurrences': len(arc_data)
                    })
               
                # Save summary file
                summary_df = pd.DataFrame(arc_summary)
                summary_file = os.path.join(self.analysis_dir, f"{type_name}_validated_all_corners_summary.csv")
                summary_df.to_csv(summary_file, index=False)
               
                # Save detailed file
                detailed_file = os.path.join(self.analysis_dir, f"{type_name}_validated_all_corners_detailed.csv")
                combined_df.to_csv(detailed_file, index=False)
               
                self.logger.info(f"  Generated: {os.path.basename(summary_file)}")
                self.logger.info(f"  Generated: {os.path.basename(detailed_file)}")
               
        except Exception as e:
            self.logger.error(f"Error generating cross-corner output for {type_name}: {str(e)}")
   
    def generate_delay_slew_overlap_output(self, overlap_arcs, delay_arcs, slew_arcs):
        """Generate output file for delay & slew overlap analysis"""
        try:
            # Create comprehensive overlap analysis
            overlap_analysis = []
           
            # Arcs in overlap
            for arc in sorted(overlap_arcs):
                overlap_analysis.append({
                    'Arc': arc,
                    'Category': 'OVERLAP',
                    'In_Delay': 'YES',
                    'In_Slew': 'YES',
                    'Description': 'Validated in both delay and slew across all corners'
                })
           
            # Arcs only in delay
            delay_only = delay_arcs - slew_arcs
            for arc in sorted(delay_only):
                overlap_analysis.append({
                    'Arc': arc,
                    'Category': 'DELAY_ONLY',
                    'In_Delay': 'YES',
                    'In_Slew': 'NO',
                    'Description': 'Validated in delay only across all corners'
                })
           
            # Arcs only in slew
            slew_only = slew_arcs - delay_arcs
            for arc in sorted(slew_only):
                overlap_analysis.append({
                    'Arc': arc,
                    'Category': 'SLEW_ONLY',
                    'In_Delay': 'NO',
                    'In_Slew': 'YES',
                    'Description': 'Validated in slew only across all corners'
                })
           
            # Save overlap analysis
            overlap_df = pd.DataFrame(overlap_analysis)
            overlap_file = os.path.join(self.analysis_dir, "delay_slew_overlap_analysis.csv")
            overlap_df.to_csv(overlap_file, index=False)
           
            # Create summary statistics
            overlap_summary = {
                'Total_Delay_Arcs': len(delay_arcs),
                'Total_Slew_Arcs': len(slew_arcs),
                'Overlap_Arcs': len(overlap_arcs),
                'Delay_Only_Arcs': len(delay_only),
                'Slew_Only_Arcs': len(slew_only),
                'Overlap_Percentage_vs_Delay': f"{len(overlap_arcs)/len(delay_arcs)*100:.1f}%" if delay_arcs else "N/A",
                'Overlap_Percentage_vs_Slew': f"{len(overlap_arcs)/len(slew_arcs)*100:.1f}%" if slew_arcs else "N/A"
            }
           
            summary_df = pd.DataFrame([overlap_summary])
            summary_file = os.path.join(self.analysis_dir, "delay_slew_overlap_summary.csv")
            summary_df.to_csv(summary_file, index=False)
           
            self.logger.info(f"  Generated: {os.path.basename(overlap_file)}")
            self.logger.info(f"  Generated: {os.path.basename(summary_file)}")
           
            # Log detailed statistics
            self.logger.info(f"  Overlap Statistics:")
            self.logger.info(f"    Total arcs in overlap: {len(overlap_arcs)}")
            self.logger.info(f"    Delay-only arcs: {len(delay_only)}")
            self.logger.info(f"    Slew-only arcs: {len(slew_only)}")
            if delay_arcs:
                self.logger.info(f"    Overlap vs Delay: {len(overlap_arcs)}/{len(delay_arcs)} ({len(overlap_arcs)/len(delay_arcs)*100:.1f}%)")
            if slew_arcs:
                self.logger.info(f"    Overlap vs Slew: {len(overlap_arcs)}/{len(slew_arcs)} ({len(overlap_arcs)/len(slew_arcs)*100:.1f}%)")
           
        except Exception as e:
            self.logger.error(f"Error generating delay-slew overlap output: {str(e)}")
   
    def generate_summary_report(self, csv_files, cross_corner_results):
        """Generate a comprehensive summary report with pass/fail ratios and cross-corner analysis"""
        self.logger.info("\n" + "="*80)
        self.logger.info("COMPREHENSIVE VALIDATION SUMMARY REPORT")
        self.logger.info("="*80)
       
        # Calculate overall statistics
        total_files = sum(stats['total_files'] for stats in self.summary_stats.values())
        total_rows = sum(stats['total_rows'] for stats in self.summary_stats.values())
        total_validated = sum(stats['validated_rows'] for stats in self.summary_stats.values())
        total_failed = sum(stats['failed_rows'] for stats in self.summary_stats.values())
       
        # Overall Summary
        self.logger.info(f"\nOVERALL SUMMARY:")
        self.logger.info(f"  Total CSV files processed: {total_files}")
        self.logger.info(f"  Total data rows processed: {total_rows}")
        if total_rows > 0:
            self.logger.info(f"  Overall pass rate: {total_validated}/{total_rows} ({total_validated/total_rows*100:.1f}%)")
            self.logger.info(f"  Overall fail rate: {total_failed}/{total_rows} ({total_failed/total_rows*100:.1f}%)")
       
        # Create summary table by Type and Corner
        self.logger.info(f"\n" + "="*80)
        self.logger.info("DETAILED SUMMARY TABLE BY TYPE AND CORNER")
        self.logger.info("="*80)
       
        # Create table header
        header = f"{'Corner':<20} {'Type':<8} {'Files':<6} {'Total':<8} {'Pass':<8} {'Fail':<8} {'Pass%':<8} {'Fail%':<8}"
        self.logger.info(header)
        self.logger.info("-" * len(header))
       
        # Sort by corner then type for consistent display
        sorted_stats = sorted(self.summary_stats.values(), key=lambda x: (x['corner'], x['type']))
       
        # Display detailed statistics
        for stats in sorted_stats:
            corner = stats['corner']
            type_name = stats['type']
            files = stats['total_files']
            total = stats['total_rows']
            validated = stats['validated_rows']
            failed = stats['failed_rows']
           
            if total > 0:
                pass_pct = f"{validated/total*100:.1f}%"
                fail_pct = f"{failed/total*100:.1f}%"
            else:
                pass_pct = "N/A"
                fail_pct = "N/A"
           
            row = f"{corner:<20} {type_name:<8} {files:<6} {total:<8} {validated:<8} {failed:<8} {pass_pct:<8} {fail_pct:<8}"
            self.logger.info(row)
       
        # Summary by Type
        self.logger.info(f"\n" + "="*60)
        self.logger.info("SUMMARY BY TYPE")
        self.logger.info("="*60)
       
        type_summary = {}
        for stats in self.summary_stats.values():
            type_name = stats['type']
            if type_name not in type_summary:
                type_summary[type_name] = {'files': 0, 'total': 0, 'validated': 0, 'failed': 0}
           
            type_summary[type_name]['files'] += stats['total_files']
            type_summary[type_name]['total'] += stats['total_rows']
            type_summary[type_name]['validated'] += stats['validated_rows']
            type_summary[type_name]['failed'] += stats['failed_rows']
       
        type_header = f"{'Type':<8} {'Files':<6} {'Total':<8} {'Pass':<8} {'Fail':<8} {'Pass%':<8} {'Fail%':<8}"
        self.logger.info(type_header)
        self.logger.info("-" * len(type_header))
       
        for type_name in sorted(type_summary.keys()):
            stats = type_summary[type_name]
            if stats['total'] > 0:
                pass_pct = f"{stats['validated']/stats['total']*100:.1f}%"
                fail_pct = f"{stats['failed']/stats['total']*100:.1f}%"
            else:
                pass_pct = "N/A"
                fail_pct = "N/A"
           
            row = f"{type_name:<8} {stats['files']:<6} {stats['total']:<8} {stats['validated']:<8} {stats['failed']:<8} {pass_pct:<8} {fail_pct:<8}"
            self.logger.info(row)
       
        # Summary by Corner
        self.logger.info(f"\n" + "="*60)
        self.logger.info("SUMMARY BY CORNER")
        self.logger.info("="*60)
       
        corner_summary = {}
        for stats in self.summary_stats.values():
            corner = stats['corner']
            if corner not in corner_summary:
                corner_summary[corner] = {'files': 0, 'total': 0, 'validated': 0, 'failed': 0}
           
            corner_summary[corner]['files'] += stats['total_files']
            corner_summary[corner]['total'] += stats['total_rows']
            corner_summary[corner]['validated'] += stats['validated_rows']
            corner_summary[corner]['failed'] += stats['failed_rows']
       
        corner_header = f"{'Corner':<20} {'Files':<6} {'Total':<8} {'Pass':<8} {'Fail':<8} {'Pass%':<8} {'Fail%':<8}"
        self.logger.info(corner_header)
        self.logger.info("-" * len(corner_header))
       
        for corner in sorted(corner_summary.keys()):
            stats = corner_summary[corner]
            if stats['total'] > 0:
                pass_pct = f"{stats['validated']/stats['total']*100:.1f}%"
                fail_pct = f"{stats['failed']/stats['total']*100:.1f}%"
            else:
                pass_pct = "N/A"
                fail_pct = "N/A"
           
            row = f"{corner:<20} {stats['files']:<6} {stats['total']:<8} {stats['validated']:<8} {stats['failed']:<8} {pass_pct:<8} {fail_pct:<8}"
            self.logger.info(row)
       
        # Cross-Corner Analysis Summary
        self.logger.info(f"\n" + "="*60)
        self.logger.info("CROSS-CORNER ANALYSIS SUMMARY")
        self.logger.info("="*60)
       
        cross_corner_header = f"{'Type':<8} {'Arcs (All Corners)':<20}"
        self.logger.info(cross_corner_header)
        self.logger.info("-" * len(cross_corner_header))
       
        for type_name in sorted(self.types):
            if type_name in cross_corner_results:
                arc_count = len(cross_corner_results[type_name])
                row = f"{type_name:<8} {arc_count:<20}"
                self.logger.info(row)
       
        # Delay & Slew Overlap Summary
        if 'delay' in cross_corner_results and 'slew' in cross_corner_results:
            delay_arcs = cross_corner_results['delay']
            slew_arcs = cross_corner_results['slew']
            overlap_arcs = delay_arcs.intersection(slew_arcs)
           
            self.logger.info(f"\nDELAY & SLEW OVERLAP:")
            self.logger.info(f"  Delay arcs (all corners): {len(delay_arcs)}")
            self.logger.info(f"  Slew arcs (all corners): {len(slew_arcs)}")
            self.logger.info(f"  Overlap arcs: {len(overlap_arcs)}")
            if delay_arcs:
                self.logger.info(f"  Overlap vs Delay: {len(overlap_arcs)}/{len(delay_arcs)} ({len(overlap_arcs)/len(delay_arcs)*100:.1f}%)")
            if slew_arcs:
                self.logger.info(f"  Overlap vs Slew: {len(overlap_arcs)}/{len(slew_arcs)} ({len(overlap_arcs)/len(slew_arcs)*100:.1f}%)")
       
        # Generate CSV summary report
        self.generate_csv_summary_report(sorted_stats, type_summary, corner_summary, cross_corner_results)
       
        # Output file locations
        self.logger.info(f"\n" + "="*60)
        self.logger.info("OUTPUT FILE LOCATIONS")
        self.logger.info("="*60)
        self.logger.info(f"Validated CSV files: {self.validated_dir}")
        self.logger.info(f"Failed CSV files: {self.failed_dir}")
        self.logger.info(f"Cross-corner analysis: {self.analysis_dir}")
        self.logger.info(f"Summary reports: {self.data_path}")
        self.logger.info(f"  - ci_validation_summary.csv")
        self.logger.info(f"  - ci_validation_summary_by_type.csv")
        self.logger.info(f"  - ci_validation_summary_by_corner.csv")
        self.logger.info(f"  - cross_corner_analysis_summary.csv")
       
    def generate_csv_summary_report(self, sorted_stats, type_summary, corner_summary, cross_corner_results):
        """Generate a CSV file with summary statistics including cross-corner analysis"""
        try:
            # Create detailed summary DataFrame
            summary_data = []
            for stats in sorted_stats:
                total = stats['total_rows']
                validated = stats['validated_rows']
                failed = stats['failed_rows']
               
                summary_data.append({
                    'Corner': stats['corner'],
                    'Type': stats['type'],
                    'Files': stats['total_files'],
                    'Total_Rows': total,
                    'Validated_Rows': validated,
                    'Failed_Rows': failed,
                    'Pass_Rate_%': round(validated/total*100, 1) if total > 0 else 0,
                    'Fail_Rate_%': round(failed/total*100, 1) if total > 0 else 0
                })
           
            # Save detailed summary
            summary_df = pd.DataFrame(summary_data)
            summary_file = os.path.join(self.data_path, 'ci_validation_summary.csv')
            summary_df.to_csv(summary_file, index=False)
           
            # Create type summary DataFrame
            type_data = []
            for type_name, stats in type_summary.items():
                total = stats['total']
                validated = stats['validated']
                failed = stats['failed']
               
                type_data.append({
                    'Type': type_name,
                    'Files': stats['files'],
                    'Total_Rows': total,
                    'Validated_Rows': validated,
                    'Failed_Rows': failed,
                    'Pass_Rate_%': round(validated/total*100, 1) if total > 0 else 0,
                    'Fail_Rate_%': round(failed/total*100, 1) if total > 0 else 0
                })
           
            type_df = pd.DataFrame(type_data)
            type_summary_file = os.path.join(self.data_path, 'ci_validation_summary_by_type.csv')
            type_df.to_csv(type_summary_file, index=False)
           
            # Create corner summary DataFrame
            corner_data = []
            for corner, stats in corner_summary.items():
                total = stats['total']
                validated = stats['validated']
                failed = stats['failed']
               
                corner_data.append({
                    'Corner': corner,
                    'Files': stats['files'],
                    'Total_Rows': total,
                    'Validated_Rows': validated,
                    'Failed_Rows': failed,
                    'Pass_Rate_%': round(validated/total*100, 1) if total > 0 else 0,
                    'Fail_Rate_%': round(failed/total*100, 1) if total > 0 else 0
                })
           
            corner_df = pd.DataFrame(corner_data)
            corner_summary_file = os.path.join(self.data_path, 'ci_validation_summary_by_corner.csv')
            corner_df.to_csv(corner_summary_file, index=False)
           
            # Create cross-corner analysis summary DataFrame
            cross_corner_data = []
            for type_name in sorted(self.types):
                if type_name in cross_corner_results:
                    arc_count = len(cross_corner_results[type_name])
                    cross_corner_data.append({
                        'Type': type_name,
                        'Arcs_Validated_All_Corners': arc_count
                    })
           
            # Add delay & slew overlap information
            if 'delay' in cross_corner_results and 'slew' in cross_corner_results:
                delay_arcs = cross_corner_results['delay']
                slew_arcs = cross_corner_results['slew']
                overlap_arcs = delay_arcs.intersection(slew_arcs)
               
                overlap_data = {
                    'Analysis_Type': 'Delay_Slew_Overlap',
                    'Delay_Arcs_All_Corners': len(delay_arcs),
                    'Slew_Arcs_All_Corners': len(slew_arcs),
                    'Overlap_Arcs': len(overlap_arcs),
                    'Delay_Only_Arcs': len(delay_arcs - slew_arcs),
                    'Slew_Only_Arcs': len(slew_arcs - delay_arcs),
                    'Overlap_vs_Delay_%': round(len(overlap_arcs)/len(delay_arcs)*100, 1) if delay_arcs else 0,
                    'Overlap_vs_Slew_%': round(len(overlap_arcs)/len(slew_arcs)*100, 1) if slew_arcs else 0
                }
               
                overlap_df = pd.DataFrame([overlap_data])
                overlap_file = os.path.join(self.data_path, 'delay_slew_overlap_summary.csv')
                overlap_df.to_csv(overlap_file, index=False)
           
            cross_corner_df = pd.DataFrame(cross_corner_data)
            cross_corner_file = os.path.join(self.data_path, 'cross_corner_analysis_summary.csv')
            cross_corner_df.to_csv(cross_corner_file, index=False)
           
            self.logger.info(f"\nCSV summary reports generated:")
            self.logger.info(f"  Detailed: {summary_file}")
            self.logger.info(f"  By Type: {type_summary_file}")
            self.logger.info(f"  By Corner: {corner_summary_file}")
            self.logger.info(f"  Cross-Corner Analysis: {cross_corner_file}")
            if 'delay' in cross_corner_results and 'slew' in cross_corner_results:
                self.logger.info(f"  Delay-Slew Overlap: {overlap_file}")
           
        except Exception as e:
            self.logger.error(f"Error generating CSV summary report: {str(e)}")
   
    def run_validation(self):
        """Main validation workflow"""
        self.logger.info("Starting CI Validation Process")
        self.logger.info(f"Data Path: {self.data_path}")
        self.logger.info(f"Types: {self.types}")
        self.logger.info(f"Corners: {self.corners}")
       
        # Step 1: Find CSV files
        csv_files = self.find_csv_files()
       
        # Step 2: Validate file existence
        if not self.validate_file_existence(csv_files):
            self.logger.error("File existence validation failed!")
            return False
       
        # Step 3: Validate CSV structure, validate CI, and generate output files
        if not self.validate_csv_structure_and_process(csv_files):
            self.logger.error("CSV structure validation and processing failed!")
            return False
       
        # Step 4: Perform cross-corner analysis
        cross_corner_results = self.perform_cross_corner_analysis()
       
        # Step 5: Generate comprehensive summary report
        self.generate_summary_report(csv_files, cross_corner_results)
       
        self.logger.info("CI Validation completed successfully!")
        return True
 
def main():
    parser = argparse.ArgumentParser(description='CI Validation Script')
    parser.add_argument('--data_path', required=True, help='Path to data directory')
    parser.add_argument('--types', nargs='+', required=True, help='List of types')
    parser.add_argument('--corners', nargs='+', required=True, help='List of corners')
    parser.add_argument('--log_file', required=True, help='Log file path')
   
    args = parser.parse_args()
   
    # Validate data path exists
    if not os.path.exists(args.data_path):
        print(f"Error: Data path '{args.data_path}' does not exist!")
        sys.exit(1)
   
    # Create validator and run validation
    validator = CIValidator(args.data_path, args.types, args.corners, args.log_file)
   
    try:
        success = validator.run_validation()
        sys.exit(0 if success else 1)
    except Exception as e:
        validator.logger.error(f"Validation failed with exception: {str(e)}")
        sys.exit(1)
 
if __name__ == "__main__":
    main()
 
