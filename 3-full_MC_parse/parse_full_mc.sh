#!/bin/bash

# Parameters
root_path="/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2025/N2P_v1.0/2-select_2nd_round/2-Full_MC_golden/"
deck_path="${root_path}/Parse/"
working_path="${root_path}/processed_MC_golden"

# Current directory for log file
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
log_file="${script_dir}/mc_golden_parse.log"

# Corners to process
corners=("ssgnp_0p450v_m40c" "ssgnp_0p465v_m40c" "ssgnp_0p480v_m40c" "ssgnp_0p495v_m40c")

# Data types to extract
types=("delay" "slew")

# Initialize log file
echo "=== MC Golden Data Parsing Log $(date) ===" > "${log_file}"
echo "Root path: ${root_path}" >> "${log_file}"
echo "Deck path: ${deck_path}" >> "${log_file}"
echo "Working path: ${working_path}" >> "${log_file}"
echo "Corners: ${corners[*]}" >> "${log_file}"
echo "Types: ${types[*]}" >> "${log_file}"
echo "=====================================" >> "${log_file}"

# Create working directory if it doesn't exist
if [ ! -d "${working_path}" ]; then
    echo "Creating working directory: ${working_path}" | tee -a "${log_file}"
    mkdir -p "${working_path}" 2>&1 | tee -a "${log_file}"
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create working directory" | tee -a "${log_file}"
        exit 1
    fi
else
    echo "Working directory already exists: ${working_path}" | tee -a "${log_file}"
fi

# Process each corner and type
for corner in "${corners[@]}"; do
    for type in "${types[@]}"; do
        output_file="${working_path}/MC_n2p_v1p0_${corner}_${type}.csv"

        echo "------------------------------------" | tee -a "${log_file}"
        echo "Processing corner: ${corner}, type: ${type}" | tee -a "${log_file}"
        echo "Output will be saved to: ${output_file}" | tee -a "${log_file}"

        # Call the Python script to parse data
        echo "Executing Python script..." | tee -a "${log_file}"
        /usr/local/python/3.9.10/bin/python3 parse_mc_golden.py \
            --corner "${corner}" \
            --type "${type}" \
            --deck_path "${deck_path}" \
            --output_file "${output_file}" \
            --log_file "${log_file}" 2>&1 | tee -a "${log_file}"

        if [ $? -eq 0 ]; then
            echo "Completed processing ${corner} ${type}" | tee -a "${log_file}"
        else
            echo "ERROR: Failed to process ${corner} ${type}" | tee -a "${log_file}"
        fi
    done
done

echo "------------------------------------" | tee -a "${log_file}"
echo "All parsing completed at $(date)" | tee -a "${log_file}"
echo "Log file: ${log_file}"
