#!/bin/bash

# Enhanced Sigma Check Script with Unified Waiver System
# Implements unified pass/fail system with structured waivers
# Generates 4 pass rates: Base, +Waiver1, Optimistic Only, +Both Waivers

# Set parameters
combined_data_root_path="/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2025/N2P_v1.0/1-MC_golden/0-FMC_golden/gen_DECKs/1-script/2-data_process/Combine_data/"

corners=("ssgnp_0p450v_m40c" "ssgnp_0p465v_m40c" "ssgnp_0p480v_m40c" "ssgnp_0p495v_m40c")
#corners=("ssgnp_0p450v_m40c")
types=("delay" "slew" "hold")  # Added hold for sigma processing

# Create a timestamp for logging
timestamp=$(date +"%Y%m%d_%H%M%S")
run_dir=$(dirname "$combined_data_root_path")
log_dir="$run_dir/logs"

# Create log directory if it doesn't exist
mkdir -p "$log_dir"
main_log="$log_dir/run_sigma_waiver_${timestamp}.log"

# Print configuration and log it
{
    echo "================================================================="
    echo "Starting SIGMA CHECK WITH UNIFIED WAIVER SYSTEM at $(date)"
    echo "================================================================="
    echo "New Features:"
    echo "  ✓ Unified pass/fail system with structured waivers"
    echo "  ✓ 4 pass rate types: Base, +Waiver1, Optimistic Only, +Both Waivers"
    echo "  ✓ Optimistic vs pessimistic error analysis"
    echo "  ✓ CI enlargement waiver (6%)"
    echo "  ✓ Enhanced visualizations with 4-bar comparison"
    echo "================================================================="
    echo "Parameters set:"
    echo "Root path: $combined_data_root_path"
    echo "Corners: ${corners[*]}"
    echo "Types: ${types[*]}"
    echo "Log directory: $log_dir"
    echo "Main log file: $main_log"
    echo "================================================================="

    # Check if the root path exists
    if [ ! -d "$combined_data_root_path" ]; then
        echo "ERROR: Root path does not exist: $combined_data_root_path"
        exit 1
    fi

    # Check for FMC RPT files with the simple pattern: fmc*{corner}*{type}*.rpt
    echo "Checking for sigma input files with pattern: 'fmc*{corner}*{type}*.rpt':"
    rpt_files_found=0

    for corner in "${corners[@]}"; do
        for type in "${types[@]}"; do
            # Simple pattern: fmc*{corner}*{type}*.rpt
            matching_files=$(find "$combined_data_root_path" -maxdepth 1 -type f -name "fmc*${corner}*${type}*.rpt" | wc -l)

            if [ "$matching_files" -gt 0 ]; then
                echo "  FOUND: $matching_files file(s) matching fmc*${corner}*${type}*.rpt"
                find "$combined_data_root_path" -maxdepth 1 -type f -name "fmc*${corner}*${type}*.rpt" | while read -r file; do
                    echo "    $(basename "$file")"
                done
                rpt_files_found=$((rpt_files_found + matching_files))
            else
                echo "  MISSING: No files matching fmc*${corner}*${type}*.rpt"
            fi
        done
    done

    echo "Total sigma RPT files found: $rpt_files_found"
    echo "================================================================="

    if [ "$rpt_files_found" -eq 0 ]; then
        echo "ERROR: No matching FMC RPT files found in $combined_data_root_path"
        exit 1
    fi

    echo "Calling SIGMA WAIVER Python script..."
    echo "================================================================="

    # Call the waiver Python script with direct arguments
    if /usr/local/python/3.9.10/bin/python3 check_sigma_with_waivers.py \
        --root_path "$combined_data_root_path" \
        --corners "${corners[@]}" \
        --types "${types[@]}" \
        --log_level INFO; then
        echo "================================================================="
        echo "Sigma waiver Python script execution completed successfully."
        echo "================================================================="

        # Check if waiver output files were generated
        if [ -f "$combined_data_root_path/sigma_PR_table_with_waivers.csv" ]; then
            echo "✓ sigma_PR_table_with_waivers.csv generated successfully"
            echo "  File size: $(du -h "$combined_data_root_path/sigma_PR_table_with_waivers.csv" | cut -f1)"
            echo "  Preview of waiver table (4 pass rates):"
            head -5 "$combined_data_root_path/sigma_PR_table_with_waivers.csv"
            echo "================================================================="
        else
            echo "⚠ WARNING: sigma_PR_table_with_waivers.csv was not generated"
        fi

        # Check for waiver summary files
        if [ -f "$combined_data_root_path/sigma_waiver_summary_table.txt" ]; then
            echo "✓ sigma_waiver_summary_table.txt generated successfully"
        fi

        if [ -f "$combined_data_root_path/optimistic_pessimistic_breakdown.txt" ]; then
            echo "✓ optimistic_pessimistic_breakdown.txt generated successfully"
            echo "  This file contains detailed optimistic vs pessimistic error analysis"
        fi

        # Check for NEW waiver visualization files
        echo ""
        echo "Generated waiver visualization files:"
        ls -la "$combined_data_root_path"/*waiver_analysis.png 2>/dev/null || echo "No waiver visualization files found"

        # Check for error distribution charts
        if [ -f "$combined_data_root_path/sigma_error_distribution_chart.png" ]; then
            echo "✓ sigma_error_distribution_chart.png generated successfully"
            echo "  Shows optimistic vs pessimistic error distribution"
        fi

        # List all generated files
        echo ""
        echo "Generated sigma waiver output files:"
        ls -la "$combined_data_root_path"/*sigma*waiver* 2>/dev/null || echo "No sigma waiver output files found"
        ls -la "$combined_data_root_path"/*optimistic_pessimistic* 2>/dev/null || echo "No breakdown files found"

    else
        echo "================================================================="
        echo "ERROR: Sigma waiver Python script execution failed with status code $?"
        echo "================================================================="
        exit 1
    fi

    echo "================================================================="
    echo "Sigma waiver check script completed at $(date)"
    echo "================================================================="
    echo ""
    echo "Summary of WAIVER SYSTEM outputs:"
    echo ""
    echo "TABLES (4 Pass Rates):"
    echo "  - sigma_PR_table_with_waivers.csv: New waiver table with 4 pass rates"
    echo "  - sigma_waiver_summary_table.txt: Human-readable summary"
    echo "  - optimistic_pessimistic_breakdown.txt: Detailed error direction analysis"
    echo ""
    echo "VISUALIZATIONS (ENHANCED - 4-BAR COMPARISON):"
    echo "  - sigma_early_sigma_waiver_analysis.png: Early_Sigma 4-bar comparison"
    echo "  - sigma_late_sigma_waiver_analysis.png: Late_Sigma 4-bar comparison"
    echo "  - sigma_error_distribution_chart.png: Optimistic vs pessimistic distribution"
    echo ""
    echo "ANALYSIS:"
    echo "  - *_sigma_check_with_waivers.csv: Individual corner/type results with waiver columns"
    echo ""
    echo "KEY FEATURES (UNIFIED WAIVER SYSTEM):"
    echo "  ✓ Base Pass = (rel_pass OR abs_pass) OR (CI bounds pass)"
    echo "  ✓ Waiver 1: CI enlargement (6%)"
    echo "  ✓ Waiver 2: Optimistic error only (lib < mc)"
    echo "  ✓ 4 pass rates: Base, +Waiver1, Optimistic Only, +Both Waivers"
    echo "  ✓ Enhanced visualizations with 4-bar comparison"
    echo "  ✓ Optimistic vs pessimistic error breakdown"
    echo "  ✓ 1-digit precision throughout"
    echo ""
    echo "Next steps:"
    echo "  1. Review sigma waiver analysis visualizations (4-bar comparison)"
    echo "  2. Analyze optimistic vs pessimistic error patterns"
    echo "  3. Use sigma_PR_table_with_waivers.csv for advanced analysis"
    echo "  4. Compare with moments waiver results for complete view"
    echo "================================================================="

} 2>&1 | tee "$main_log"

echo "Sigma waiver log file saved to: $main_log"