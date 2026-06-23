#!/bin/bash
 
# Enhanced Sigma Check Script
# Supports the new features: moments-only table, 1-digit precision, visual tier analysis
 
# Set parameters
# set base_dir = "/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2024/N2P"
 
combined_data_root_path="/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2025/N2P_v1.0/1-MC_golden/0-FMC_golden/gen_DECKs/1-script/2-data_process/Combine_data/"
 
corners=("ssgnp_0p450v_m40c" "ssgnp_0p465v_m40c" "ssgnp_0p480v_m40c" "ssgnp_0p495v_m40c")
#corners=("ssgnp_0p450v_m40c")
types=("delay" "slew" "hold")  # Added hold for sigma processing
 
# Create a timestamp for logging
timestamp=$(date +"%Y%m%d_%H%M%S")
run_dir=$(dirname "$combined_data_root_path")
log_dir="$run_dir/logs"
 
# Create log directory if it doesn't exist
mkdir -p "$log_dir"
main_log="$log_dir/run_enhanced_sigma_${timestamp}.log"
 
# Print configuration and log it
{
    echo "================================================================="
    echo "Starting ENHANCED sigma check script at $(date)"
    echo "================================================================="
    echo "New Features:"
    echo "  âœ“ 1-digit precision for all pass rates"
    echo "  âœ“ sigma_PR_table_moments.csv (delay/slew only)"
    echo "  âœ“ Visual tier analysis charts"
    echo "  âœ“ Tier effectiveness heatmaps"
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
                echo "  FOUND: $matching_files file(s) matching fmc*${corner}*${type}*.rpt"
                find "$combined_data_root_path" -maxdepth 1 -type f -name "fmc*${corner}*${type}*.rpt" | while read -r file; do
                    echo "    $(basename "$file")"
                done
                rpt_files_found=$((rpt_files_found + matching_files))
            else
                echo "  MISSING: No files matching fmc*${corner}*${type}*.rpt"
            fi
        done
    done
 
    echo "Total sigma RPT files found: $rpt_files_found"
    echo "================================================================="
 
    # Debug: Show what files are actually available
    echo "DEBUG: All .rpt files in directory:"
    ls -1 "$combined_data_root_path"/*.rpt 2>/dev/null | head -10 || echo "No .rpt files found"
    echo "================================================================="
 
    if [ "$rpt_files_found" -eq 0 ]; then
        echo "ERROR: No matching FMC RPT files found in $combined_data_root_path"
        echo "Expected pattern: fmc*{corner}*{type}*.rpt"
        echo "Available .rpt files:"
        ls -la "$combined_data_root_path"/*.rpt 2>/dev/null || echo "No .rpt files found"
        echo ""
        echo "Available FMC files:"
        ls -la "$combined_data_root_path"/*fmc* 2>/dev/null || echo "No FMC files found"
        exit 1
    fi
 
    echo "Calling ENHANCED sigma Python script..."
    echo "================================================================="
 
    # Call the enhanced Python script with direct arguments
    if /usr/local/python/3.9.10/bin/python3 check_sigma.py \
        --root_path "$combined_data_root_path" \
        --corners "${corners[@]}" \
        --types "${types[@]}" \
        --log_level INFO; then
        echo "================================================================="
        echo "Enhanced sigma Python script execution completed successfully."
        echo "================================================================="
 
        # Check if both sigma_PR_table files were generated
        if [ -f "$combined_data_root_path/sigma_PR_table.csv" ]; then
            echo "âœ“ sigma_PR_table.csv generated successfully (all types)"
            echo "  File size: $(du -h "$combined_data_root_path/sigma_PR_table.csv" | cut -f1)"
            echo "  Preview of sigma_PR_table.csv:"
            head -5 "$combined_data_root_path/sigma_PR_table.csv"
            echo "================================================================="
        else
            echo "âš  WARNING: sigma_PR_table.csv was not generated"
        fi
 
        # Check for the new moments-only table
        if [ -f "$combined_data_root_path/sigma_PR_table_moments.csv" ]; then
            echo "âœ“ sigma_PR_table_moments.csv generated successfully (delay/slew only)"
            echo "  File size: $(du -h "$combined_data_root_path/sigma_PR_table_moments.csv" | cut -f1)"
            echo "  This file is for moments integration (excludes hold data)"
            echo "  Preview of sigma_PR_table_moments.csv:"
            head -5 "$combined_data_root_path/sigma_PR_table_moments.csv"
            echo "================================================================="
        else
            echo "âš  WARNING: sigma_PR_table_moments.csv was not generated"
        fi
 
        # Check for summary files
        if [ -f "$combined_data_root_path/sigma_summary_table.txt" ]; then
            echo "âœ“ sigma_summary_table.txt generated successfully (1-digit precision)"
        fi
 
        if [ -f "$combined_data_root_path/sigma_summary_table.csv" ]; then
            echo "âœ“ sigma_summary_table.csv generated successfully (1-digit precision)"
        fi
 
        if [ -f "$combined_data_root_path/sigma_tier_analysis.txt" ]; then
            echo "âœ“ sigma_tier_analysis.txt generated successfully (1-digit precision)"
            echo "  This file contains detailed tier-by-tier pass rate analysis"
        fi
 
        # Check for NEW visualization files (updated naming)
        if [ -f "$combined_data_root_path/sigma_early_sigma_tier_analysis.png" ]; then
            echo "âœ“ sigma_early_sigma_tier_analysis.png generated successfully"
            echo "  Shows: DELAY and SLEW Early_Sigma across all corners"
            file_size=$(du -h "$combined_data_root_path/sigma_early_sigma_tier_analysis.png" | cut -f1)
            echo "  File size: $file_size"
        fi
 
        if [ -f "$combined_data_root_path/sigma_late_sigma_tier_analysis.png" ]; then
            echo "âœ“ sigma_late_sigma_tier_analysis.png generated successfully"
            echo "  Shows: DELAY, SLEW, and HOLD Late_Sigma across all corners"
            file_size=$(du -h "$combined_data_root_path/sigma_late_sigma_tier_analysis.png" | cut -f1)
            echo "  File size: $file_size"
        fi
 
        if [ -f "$combined_data_root_path/sigma_pass_rate_heatmap.png" ]; then
            echo "âœ“ sigma_pass_rate_heatmap.png generated successfully"
            echo "  Clean summary heatmap showing final pass rates only"
            file_size=$(du -h "$combined_data_root_path/sigma_pass_rate_heatmap.png" | cut -f1)
            echo "  File size: $file_size"
        fi
 
        # List all generated files
        echo "Generated sigma output files:"
        ls -la "$combined_data_root_path"/*sigma* 2>/dev/null || echo "No sigma output files found"
 
        # Show PNG files separately
        echo ""
        echo "Generated visualization files:"
        ls -la "$combined_data_root_path"/*.png 2>/dev/null || echo "No PNG visualization files found"
 
    else
        echo "================================================================="
        echo "ERROR: Enhanced sigma Python script execution failed with status code $?"
        echo "================================================================="
        exit 1
    fi
 
    echo "================================================================="
    echo "Enhanced sigma check script completed at $(date)"
    echo "================================================================="
    echo ""
    echo "Summary of ENHANCED outputs:"
    echo ""
    echo "TABLES (1-digit precision):"
    echo "  - sigma_PR_table.csv: Complete table (delay/slew/hold)"
    echo "  - sigma_PR_table_moments.csv: For moments integration (delay/slew only)"
    echo "  - sigma_summary_table.txt: Human-readable summary"
    echo "  - sigma_summary_table.csv: Machine-readable summary"
    echo ""
    echo "VISUALIZATIONS (OPTIMIZED - 2 FILES TOTAL):"
    echo "  - sigma_early_sigma_tier_analysis.png: DELAY + SLEW Early_Sigma (all corners)"
    echo "  - sigma_late_sigma_tier_analysis.png: DELAY + SLEW + HOLD Late_Sigma (all corners)"
    echo "  - sigma_pass_rate_heatmap.png: Clean summary heatmap"
    echo ""
    echo "ANALYSIS:"
    echo "  - sigma_tier_analysis.txt: Detailed tier-by-tier analysis"
    echo "  - *_sigma_check_info.csv: Individual corner/type results"
    echo ""
    echo "KEY FEATURES (FINAL OPTIMIZED VERSION):"
    echo "  âœ“ Four-tier checking with CI enlargement"
    echo "  âœ“ 1-digit precision throughout"
    echo "  âœ“ Separate table for moments integration (no hold)"
    echo "  âœ“ OPTIMIZED: Only 2 visualization files total"
    echo "  âœ“ FIXED: Larger legends, no title overlap, proper spacing"
    echo "  âœ“ ORGANIZED: Type â†’ Corner grouping with visual separators"
    echo "  âœ“ CDNS/SNPS auto-detection"
    echo ""
    echo "Next steps:"
    echo "  1. Review sigma_early_sigma_tier_analysis.png (delay + slew analysis)"
    echo "  2. Review sigma_late_sigma_tier_analysis.png (all types analysis)"
    echo "  3. Use sigma_PR_table_moments.csv for check_moments.py"
    echo "  4. Run check_moments.py for complete certification analysis"
    echo "================================================================="
 
} 2>&1 | tee "$main_log"
 
echo "Enhanced sigma log file saved to: $main_log"
 
