#!/bin/bash
 
# Set parameters
set base_dir = "/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2024/N2P"
### CDNS
#combined_data_root_path="/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2024/N2P/7-final_results/1-CDNS/R1/moments"
 
### SNPS
combined_data_root_path="/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2024/N2P/7-final_results/2-SNPS/R4/moments"
 
corners=("ssgnp_0p450v_m40c" "ssgnp_0p465v_m40c" "ssgnp_0p480v_m40c" "ssgnp_0p495v_m40c")
#corners=("ssgnp_0p450v_m40c")
types=("delay" "slew")
 
# Create a timestamp for logging
timestamp=$(date +"%Y%m%d_%H%M%S")
run_dir=$(dirname "$combined_data_root_path")
log_dir="$run_dir/logs"
 
# Create log directory if it doesn't exist
mkdir -p "$log_dir"
main_log="$log_dir/run_${timestamp}.log"
 
# Export variables so they can be used by other scripts
export combined_data_root_path
export corners
export types
export timestamp
export log_dir
 
# Print confirmation and log it
{
    echo "=========================================================="
    echo "Starting parameter check script at $(date)"
    echo "=========================================================="
    echo "Parameters set:"
    echo "Root path: $combined_data_root_path"
    echo "Corners: ${corners[*]}"
    echo "Types: ${types[*]}"
    echo "Log directory: $log_dir"
    echo "Main log file: $main_log"
    echo "=========================================================="
   
    # Check if the root path exists
    if [ ! -d "$combined_data_root_path" ]; then
        echo "ERROR: Root path does not exist: $combined_data_root_path"
        exit 1
    fi
   
    # Check for RPT files
    echo "Checking for input files with pattern: 'MC*{corner}*{type}*.rpt':"
    rpt_files_found=0
   
    for corner in "${corners[@]}"; do
        for type in "${types[@]}"; do
            # Use find with wildcard matching - note the pattern allows type in the middle
            matching_files=$(find "$combined_data_root_path" -maxdepth 1 -type f -name "MC*${corner}*${type}*.rpt" | wc -l)
           
            if [ "$matching_files" -gt 0 ]; then
                echo "  FOUND: $matching_files file(s) matching MC*${corner}*${type}*.rpt"
                find "$combined_data_root_path" -maxdepth 1 -type f -name "MC*${corner}*${type}*.rpt" | while read -r file; do
                    echo "    - $(basename "$file")"
                done
                rpt_files_found=$((rpt_files_found + matching_files))
            else
                echo "  MISSING: No files matching MC*${corner}*${type}*.rpt"
            fi
        done
    done
   
    echo "Total RPT files found: $rpt_files_found"
    echo "=========================================================="
   
    if [ "$rpt_files_found" -eq 0 ]; then
        echo "ERROR: No matching RPT files found in $combined_data_root_path"
        exit 1
    fi
   
    echo "Calling Python script..." 
    # Call the Python script with proper error handling
    if /usr/local/python/3.9.10/bin/python3 check_moments.py; then
        echo "Python script execution completed successfully."
    else
        echo "ERROR: Python script execution failed with status code $?"
    fi
   
    echo "=========================================================="
    echo "Script completed at $(date)"
    echo "=========================================================="
} 2>&1 | tee "$main_log"
 
echo "Log file saved to: $main_log"
 
