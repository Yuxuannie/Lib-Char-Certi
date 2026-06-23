#!/bin/bash
 
# Configuration
INPUT_FILE="/SIM/DFDS_20211231/Personal/ritaliu/LDBX_scripts/get_arc_points/fmc_result_n2p_v0p9_ssgnp_0p450v_m40c_delay_fmc_lib_comp.rpt"    # Change this to your actual file name
OUTPUT_FILE="sorted_file.rpt"
DELIMITER=' '            # Adjust this to your actual delimiter
SORT_COLUMN=6            # Column number to sort by (1-based index)
 
# Check if the input file exists
if [[ ! -f "$INPUT_FILE" ]]; then
  echo "Error: File '$INPUT_FILE' not found."
  exit 1
fi
 
# Sort the file and format it for columnar output
{
  head -n 1 "$INPUT_FILE"                               # Output the header
  tail -n +2 "$INPUT_FILE" |                            # Output the rest of the file
  sort -k"$SORT_COLUMN" -r -n                           # Sort by the specified column
} | column -t > "$OUTPUT_FILE"                          # Align columns with `column -t`
 
# Use less to view the output in a scrollable and user-friendly way
less -S "$OUTPUT_FILE"
 
# Optional: Clean up the sorted output file if you don't need to keep it
# rm "$OUTPUT_FILE"
 
