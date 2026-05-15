#!/bin/bash
 
# Configuration parameters
working_path="/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2025/N2P_v1.0/1-MC_golden/1-Full_MC_golden/"
#corners=("ssgnp_0p465v_m40c" "ssgnp_0p480v_m40c" )
corners=("ssgnp_0p450v_m40c")
script_path="/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2025/N2P_v1.0/1-MC_golden/1-Full_MC_golden/0-script/1-Parse/"
specific_arcs=""
#specific_arcs="combinational_FA1MDLIMZD4BWP130HPNPN3P48CPD_S_fall_CI_fall_A_B_4-4 combinational_FA1MDLIMZD4BWP130HPNPN3P48CPD_S_rise_CI_rise_A_B_5-5 combinational_XNR4MDLIMZD4BWP130HPNPN3P48CPD_ZN_fall_A2_rise_notA1_notA3_notA4_6-6"
 
# Divider function for log file
print_divider() {
    echo "=================================================================" >> $log_file
}
 
print_section_header() {
    print_divider
    echo "                     $1                                          " >> $log_file
    print_divider
}
 
# Log file setup
log_file="${script_path}/parse_mc_data.log"
timestamp=$(date +"%Y-%m-%d %H:%M:%S")
 
# Clear log file and start new log
echo "[$timestamp] MC DATA PARSING JOB STARTED" > $log_file
print_divider
 
# Log settings
echo "[$timestamp] Configuration:" >> $log_file
echo "[$timestamp] Working path: $working_path" >> $log_file
echo "[$timestamp] Script path: $script_path" >> $log_file
echo "[$timestamp] Corners to process: ${corners[*]}" >> $log_file
if [ -n "$specific_arcs" ]; then
    # Convert comma-separated list to array
    IFS=',' read -ra arc_array <<< "$specific_arcs"
    echo "[$timestamp] Specific arcs to process: ${arc_array[*]}" >> $log_file
else
    echo "[$timestamp] Processing all arcs" >> $log_file
fi
print_divider
 
# Create main output directory if it doesn't exist
mkdir -p "${working_path}/Parse"
 
# Path to Python script
python_script="${script_path}/parse_mc_data.py"
 
# Process each corner
for corner in "${corners[@]}"; do
    print_section_header "PROCESSING CORNER: $corner"
    echo "[$timestamp] Processing corner: $corner" >> $log_file
   
    # Set the running path for this corner
    running_path="${working_path}/${corner}"
   
    # Check if corner directory exists
    if [ ! -d "$running_path" ]; then
        echo "[$timestamp] ERROR: Corner directory not found: $running_path" >> $log_file
        continue
    fi
   
    # Create corner directory in OUTPUT
    mkdir -p "${working_path}/Parse/${corner}"
   
    # Process each arc subdirectory
    echo "[$timestamp] Searching for arc directories in $running_path" >> $log_file
    arc_count=0
    success_count=0
    error_count=0
   
    print_divider
   
    # Find all directories in the running path
    for arc_dir in "$running_path"/*/ ; do
        if [ -d "$arc_dir" ]; then
            arc_name=$(basename "$arc_dir")
           
            # Check if we should process only specific arcs
            if [ -n "$specific_arcs" ]; then
                # Check if the current arc is in the list of specific arcs
                if ! echo "$specific_arcs" | grep -q -w "$arc_name"; then
                    # Skip this arc if it's not in the list
                    continue
                fi
            fi
           
            echo "[$timestamp] Processing arc: $arc_name" >> $log_file
           
            # Check if required files exist
            mc_sim_file="${arc_dir}/mc_sim.sp"
            report_file="${arc_dir}/OUT.ava.report"
           
            if [ ! -f "$mc_sim_file" ] || [ ! -f "$report_file" ]; then
                echo "[$timestamp] WARNING: Required files not found in arc: $arc_name" >> $log_file
                ((error_count++))
                continue
            fi
           
            # Create subdirectory for this arc
            arc_dir_output="${working_path}/Parse/${corner}/${arc_name}"
            mkdir -p "$arc_dir_output"
           
            # Define output files for this arc
            csv_output="${arc_dir_output}/stats.csv"
            txt_output="${arc_dir_output}/netlist_params.txt"
           
            # Call Python script to parse the files
            /usr/local/python/3.9.10/bin/python3 $python_script "$mc_sim_file" "$report_file" "$csv_output" "$txt_output" "$arc_name" "$corner" >> $log_file 2>&1
           
            if [ $? -eq 0 ]; then
                ((arc_count++))
                ((success_count++))
                echo "[$timestamp] SUCCESS: Processed arc: $arc_name" >> $log_file
            else
                echo "[$timestamp] ERROR: Python script failed for arc: $arc_name" >> $log_file
                ((error_count++))
            fi
           
            # Add a small separator between arcs for better readability
            echo "-----------------------------------------------------------------" >> $log_file
        fi
    done
   
    print_divider
    echo "[$timestamp] Completed processing corner: $corner" >> $log_file
    echo "[$timestamp] Total arcs found: $arc_count" >> $log_file
    echo "[$timestamp] Successfully processed: $success_count" >> $log_file
    echo "[$timestamp] Errors/warnings: $error_count" >> $log_file
    print_divider
done
 
print_section_header "JOB SUMMARY"
echo "[$timestamp] Job completed. Results saved to ${working_path}/Parse/" >> $log_file
if [ -n "$specific_arcs" ]; then
    echo "[$timestamp] Processed specific arcs: $specific_arcs" >> $log_file
else
    echo "[$timestamp] Processed all arcs in each corner" >> $log_file
fi
echo "[$timestamp] Results are organized by corner and arc in ${working_path}/Parse/" >> $log_file
print_divider
 
echo "[$timestamp] Usage examples:" >> $log_file
echo "[$timestamp] Process all arcs in all corners: $0" >> $log_file
echo "[$timestamp] Process specific corners: $0 -c ssgnp_0p450v_m40c,ssgnp_0p465v_m40c" >> $log_file
echo "[$timestamp] Process specific arcs across all corners: $0 -a arc1,arc2,arc3" >> $log_file
echo "[$timestamp] Process specific arcs in specific corners: $0 -c ssgnp_0p450v_m40c -a arc1,arc2" >> $log_file
print_divider
 
 
 
