#!/bin/bash
 
# CI Validation Shell Script
# This script defines parameters and calls the Python validation script
 
# Define parameters
DATA_PATH="/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2025/N2P_v1.0/1-MC_golden/0-FMC_golden/gen_DECKs/1-script/2-data_process/Combine_data/"
 
# Define types array
TYPES=("delay" "slew" "hold" "mpw")
 
# Define corners array
CORNERS=("ssgnp_0p450v_m40c" "ssgnp_0p465v_m40c" "ssgnp_0p480v_m40c" "ssgnp_0p495v_m40c")
 
# Define log file path
LOG_FILE="./ci_validation_$(date +%Y%m%d_%H%M%S).log"
 
# Create log file and add header
echo "CI Validation Log - $(date)" > "$LOG_FILE"
echo "Data Path: $DATA_PATH" >> "$LOG_FILE"
echo "Types: ${TYPES[*]}" >> "$LOG_FILE"
echo "Corners: ${CORNERS[*]}" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
 
# Print information to console
echo "Starting CI Validation..."
echo "Data Path: $DATA_PATH"
echo "Types: ${TYPES[*]}"
echo "Corners: ${CORNERS[*]}"
echo "Log File: $LOG_FILE"
echo ""
 
# Check if Python script exists
PYTHON_SCRIPT="ci_validation.py"
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Error: Python script '$PYTHON_SCRIPT' not found!"
    echo "Error: Python script '$PYTHON_SCRIPT' not found!" >> "$LOG_FILE"
    exit 1
fi
 
# Check if data path exists
if [ ! -d "$DATA_PATH" ]; then
    echo "Error: Data path '$DATA_PATH' does not exist!"
    echo "Error: Data path '$DATA_PATH' does not exist!" >> "$LOG_FILE"
    exit 1
fi
 
# Call Python script with parameters
echo "Calling Python validation script..."
/usr/local/python/3.9.10/bin/python3 "$PYTHON_SCRIPT" \
    --data_path "$DATA_PATH" \
    --types "${TYPES[@]}" \
    --corners "${CORNERS[@]}" \
    --log_file "$LOG_FILE"
 
# Check Python script exit status
if [ $? -eq 0 ]; then
    echo "CI Validation completed successfully!"
    echo "CI Validation completed successfully!" >> "$LOG_FILE"
    echo ""
    echo "Output Structure:"
    echo "  - Validated CSV files saved to: $DATA_PATH/validated/"
    echo "  - Failed CSV files saved to: $DATA_PATH/failed/"
    echo "  - Cross-corner analysis saved to: $DATA_PATH/cross_corner_analysis/"
    echo "    * {type}_validated_all_corners_summary.csv (for each type)"
    echo "    * {type}_validated_all_corners_detailed.csv (for each type)"
    echo "    * delay_slew_overlap_analysis.csv"
    echo "    * delay_slew_overlap_summary.csv"
    echo "  - Summary reports saved to: $DATA_PATH/"
    echo "    * ci_validation_summary.csv (detailed breakdown)"
    echo "    * ci_validation_summary_by_type.csv (aggregated by type)"
    echo "    * ci_validation_summary_by_corner.csv (aggregated by corner)"
    echo "    * cross_corner_analysis_summary.csv (cross-corner stats)"
    echo "    * delay_slew_overlap_summary.csv (delay & slew overlap stats)"
else
    echo "CI Validation failed!"
    echo "CI Validation failed!" >> "$LOG_FILE"
    exit 1
fi
 
echo "Log file saved to: $LOG_FILE"
 
