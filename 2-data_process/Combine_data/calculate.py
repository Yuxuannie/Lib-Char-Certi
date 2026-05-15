import os
import re
import sys
import csv
 
def parse_fmc_log(folder_path, file_name, csv_writer, log, node, corner, type_info):
    log_file_path = os.path.join(folder_path, file_name, 'fastmontecarlo.log')
    arc_name = re.sub(r'(\d)-(\d)', r'\1_\2', file_name)
    print(f"Debug: Parsing file {log_file_path} for arc {arc_name}", file=log)
 
    try:
        with open(log_file_path, 'r') as fin:
            lines = fin.readlines()
    except FileNotFoundError:
        print(f"Error: Log file {log_file_path} not found.", file=log)
        return None
 
    FMC_result = {}
    parsing = False
    done_list = []
    section_found = False
 
    output_name_map = {
        'delay': 'meas_delay',
        'slew': 'meas_tt_out',
        'seq_delay': 'cp2q',
        'hold': 'cp2d'
    }
    output_name = output_name_map.get(type_info, 'unknown')
    print(f"Debug: Looking for output_name {output_name}", file=log)
 
    for line in lines:
        if f"STATISTICAL BEHAVIOR FOR MEASUREMENT {output_name}" in line:
            parsing = True
            done_list.append(arc_name)
            FMC_result[arc_name] = {}
            section_found = True
            print(f"\n--- Start of section for {arc_name} ---", file=log)
            continue
 
        if parsing:
            parse_fmc_line(line, FMC_result, arc_name)
 
            if "Max Percentile UB" in line:
                parsing = False
                print(f"--- End of section for {arc_name} at 'Max Percentile UB' ---\n", file=log)
                continue
 
    if not section_found:
        print(f"Warning: Statistical behavior section not found for arc {arc_name}", file=log)
        return None
 
    cell_name, out_pin, out_pin_direction, rel_pin, rel_pin_direction, when, fir_index, sec_index = parse_arc_info(arc_name)
    print(f"Debug: Output pin direction for {arc_name} is {out_pin_direction}", file=log)
 
    if type_info == 'delay' and out_pin_direction == 'rise':
        table_type = 'cell_rise'
    elif type_info == 'delay' and out_pin_direction == 'fall':
        table_type = 'cell_fall'
    elif type_info == 'slew' and out_pin_direction == 'rise':
        table_type = 'rise_transition'
    elif type_info == 'slew' and out_pin_direction == 'fall':
        table_type = 'fall_transition'
    else:
        table_type = 'unknown'
 
    if arc_name in done_list:
        mc_nominal = FMC_result[arc_name].get('nominal', 0)
        mc_early_sigma_ub = (mc_nominal - FMC_result[arc_name].get('min_per_ub', 0)) / 3
        mc_early_sigma_lb = (mc_nominal - FMC_result[arc_name].get('min_per_lb', 0)) / 3
        mc_early_sigma = (mc_early_sigma_ub + mc_early_sigma_lb) / 2
 
        mc_late_sigma_ub = (FMC_result[arc_name].get('max_per_ub', 0) - mc_nominal) / 3
        mc_late_sigma_lb = (FMC_result[arc_name].get('max_per_lb', 0) - mc_nominal) / 3
        mc_late_sigma = (mc_late_sigma_ub + mc_late_sigma_lb) / 2
 
        report_data = [
            arc_name, cell_name, out_pin, rel_pin, out_pin_direction, rel_pin_direction, when, fir_index, sec_index,
            mc_nominal, mc_early_sigma, mc_early_sigma_ub, mc_early_sigma_lb,
            mc_late_sigma, mc_late_sigma_ub, mc_late_sigma_lb,
            FMC_result[arc_name].get('mean', 0) - mc_nominal, FMC_result[arc_name].get('mean_ub', 0) - mc_nominal, FMC_result[arc_name].get('mean_lb', 0) - mc_nominal,
            FMC_result[arc_name].get('std', 0), FMC_result[arc_name].get('std_ub', 0), FMC_result[arc_name].get('std_lb', 0),
            FMC_result[arc_name].get('skew', 0), FMC_result[arc_name].get('skew_ub', 0), FMC_result[arc_name].get('skew_lb', 0),
            table_type
        ]
 
        print(f"Debug: Writing report data for {arc_name}: {report_data}", file=log)
        csv_writer.writerow(report_data)
    return arc_name
 
def parse_summary_csv(folder_path, file_name, csv_writer, log, node, corner, type_info, done_list, missing_arcs):
    csv_files = [f for f in os.listdir(os.path.join(folder_path, file_name)) if f.startswith("summary") and f.endswith(".csv")]
    if not csv_files:
        print(f"Error: No summary.*.csv files found in {os.path.join(folder_path, file_name)}", file=log)
        missing_arcs.append(file_name)
        return None
 
    largest_csv = max(csv_files, key=lambda f: int(re.search(r'\d+', f).group()))
    csv_file_path = os.path.join(folder_path, file_name, largest_csv)
    arc_name = re.sub(r'(\d)-(\d)', r'\1_\2', file_name)
    print(f"Debug: Parsing file {csv_file_path} for arc {arc_name}", file=log)
 
    try:
        with open(csv_file_path, 'r') as fin:
            lines = fin.readlines()
    except FileNotFoundError:
        print(f"Error: CSV file {csv_file_path} not found.", file=log)
        missing_arcs.append(file_name)
        return None
 
    header = lines[0].strip().split(',')
    try:
        if type_info == 'hold' or type_info == "mpw":
            nominal_index = header.index('Nominal')
            percentile_lb_index = header.index('Percentile LB')
            percentile_ub_index = header.index('Percentile UB')
    except ValueError as e:
        print(f"Error: Missing expected column in header for {type_info}: {e}", file=log)
        missing_arcs.append(file_name)
        return None
 
    try:
        data_line = lines[1].strip().split(',')
        if type_info == 'hold' or type_info == "mpw":
            nominal = float(data_line[nominal_index]) * 1e12
            percentile_lb = float(data_line[percentile_lb_index]) * 1e12
            percentile_ub = float(data_line[percentile_ub_index]) * 1e12
    except (IndexError, ValueError) as e:
        print(f"Error: Issue with data line in {csv_file_path} for {type_info}: {e}", file=log)
        missing_arcs.append(file_name)
        return None
 
    cell_name, out_pin, out_pin_direction, rel_pin, rel_pin_direction, when, fir_index, sec_index = parse_arc_info(arc_name)
    print(f"Debug: Output pin direction for {arc_name} is {out_pin_direction}", file=log)
 
    if type_info == 'hold':
        if out_pin_direction == 'rise':
            table_type = 'rise_constraint'
        elif out_pin_direction == 'fall':
            table_type = 'fall_constraint'
        else:
            table_type = 'unknown'
    elif type_info == 'mpw':
        if out_pin_direction == 'rise':
            table_type = 'rise_constraint'
        elif out_pin_direction == 'fall':
            table_type = 'fall_constraint'
        else:
            table_type = 'unknown'
 
    if type_info == 'hold' or type_info == "mpw":
        mc_late_sigma_ub = (percentile_ub - nominal) / 3
        mc_late_sigma_lb = (percentile_lb - nominal) / 3
        mc_late_sigma = (mc_late_sigma_ub + mc_late_sigma_lb) / 2
        report_data = [
            arc_name, cell_name, out_pin, rel_pin, out_pin_direction, rel_pin_direction, when, fir_index, sec_index,
            nominal, mc_late_sigma, mc_late_sigma_ub, mc_late_sigma_lb,
            table_type
        ]
 
    print(f"Debug: Writing report data for {arc_name}: {report_data}", file=log)
    csv_writer.writerow(report_data)
 
    done_list.append(file_name)
    return arc_name
 
def parse_fmc_line(line, FMC_result, arc_name):
    if "Nominal" in line:
        nominal = line.split()[-1]
        FMC_result[arc_name]['nominal'] = 1e12 * float(nominal)
    if "Mean LB" in line:
        mean_lb = line.split()[-1]
        FMC_result[arc_name]['mean_lb'] = 1e12 * float(mean_lb)
    if "Mean UB" in line:
        mean_ub = line.split()[-1]
        FMC_result[arc_name]['mean_ub'] = 1e12 * float(mean_ub)
    if "Mean   " in line:
        mean = line.split()[-1]
        FMC_result[arc_name]['mean'] = 1e12 * float(mean)
    if "Stddev LB" in line:
        std_lb = line.split()[-1]
        FMC_result[arc_name]['std_lb'] = 1e12 * float(std_lb)
    if "Stddev UB" in line:
        std_ub = line.split()[-1]
        FMC_result[arc_name]['std_ub'] = 1e12 * float(std_ub)
    if "Stddev   " in line:
        std = line.split()[-1]
        FMC_result[arc_name]['std'] = 1e12 * float(std)
    if "Skewness LB" in line:
        skew_lb = line.split()[-1]
        FMC_result[arc_name]['skew_lb'] = float(skew_lb)
    if "Skewness UB" in line:
        skew_ub = line.split()[-1]
        FMC_result[arc_name]['skew_ub'] = float(skew_ub)
    if "Skewness   " in line:
        skew = line.split()[-1]
        FMC_result[arc_name]['skew'] = float(skew)
    if "Min Percentile LB" in line:
        min_per_lb = line.split()[-1]
        FMC_result[arc_name]['min_per_lb'] = 1e12 * float(min_per_lb)
    if "Min Percentile UB" in line:
        min_per_ub = line.split()[-1]
        FMC_result[arc_name]['min_per_ub'] = 1e12 * float(min_per_ub)
    if "Min Percentile   " in line:
        min_per = line.split()[-1]
        FMC_result[arc_name]['min_per'] = 1e12 * float(min_per)
    if "Max Percentile LB" in line:
        max_per_lb = line.split()[-1]
        FMC_result[arc_name]['max_per_lb'] = 1e12 * float(max_per_lb)
    if "Max Percentile UB" in line:
        max_per_ub = line.split()[-1]
        FMC_result[arc_name]['max_per_ub'] = 1e12 * float(max_per_ub)
    if "Max Percentile   " in line:
        max_per = line.split()[-1]
        FMC_result[arc_name]['max_per'] = 1e12 * float(max_per)
 
def parse_arc_info(key):
    parts = key.split("_")
   
    # Detect the type of arc and adjust parsing for `mpw` (minimum pulse width) if necessary
    if parts[0] == 'min' and parts[1] == 'pulse':  # Specifically for `mpw` arcs
        timing_type = parts[0:2]  # Combine `min` and `pulse` to form timing type
        cell_name = parts[3]
        out_pin = parts[4]
        out_pin_direction = parts[5]
        rel_pin = parts[6]
        rel_pin_direction = parts[7]
        when_condition = parts[8:][:-3]  # Extract condition and exclude indices
        fir_index = parts[-3]
        sec_index = parts[-2]
    else:  # Default parsing for other types of arcs
        timing_type = parts[0]
        cell_name = parts[1]
        out_pin = parts[2]
        out_pin_direction = parts[3]
        rel_pin = parts[4]
        rel_pin_direction = parts[5]
        when_condition = parts[6:][:-2]
        fir_index = parts[-2]
        sec_index = parts[-1]
 
    # Process the `when_condition` to handle "NO CONDITION" or custom cases
    if len(when_condition) > 1 and when_condition[0] == 'NO' and when_condition[1] == 'CONDITION':
        when = 'None'
    else:
        replaced_list = [item.replace('not', '!') for item in when_condition]
        when = '&'.join(replaced_list)
 
    result = (cell_name, out_pin, out_pin_direction, rel_pin, rel_pin_direction, when, fir_index, sec_index)
 
    print(f"Debug: Parsed arc info: {result}")
    return result
 
def main(node, corner, folder_path, type_info):
    print(f"Debug: Starting process with node: {node}, corner: {corner}, folder_path: {folder_path}, type_info: {type_info}")
    file_list = [f for f in os.listdir(folder_path) if f.startswith(("combinational_", "edge_", "hold_","min_pulse_width"))]
 
    print(f"The number of files in the folder path are: {len(file_list)}")
    report_file = f'fmc_result_{node}_{corner}_{type_info}.csv'
    log_file = f'data_run_{node}_{corner}_{type_info}.log'
 
    with open(report_file, 'w', newline='') as csvfile, open(log_file, 'w') as log:
        csv_writer = csv.writer(csvfile)
        done_list = []
        missing_arcs = []
 
        header_written = False
 
        for file_name in file_list:
            if not header_written:
                if type_info in ['delay', 'slew']:
                    header = [
                        "Arc", "Cell_Name", "output_pin", "rel_pin", "output_pin_dir", "rel_pin_dir", "when", "first_index", "sec_index",
                        "MC_Nominal", "MC_Early_Sigma", "MC_Early_Sigma_UB", "MC_Early_Sigma_LB",
                        "MC_Late_Sigma", "MC_Late_Sigma_UB", "MC_Late_Sigma_LB",
                        "MC_Meansht", "MC_Meansht_UB", "MC_Meansht_LB",
                        "MC_Std", "MC_Std_UB", "MC_Std_LB",
                        "MC_Skew", "MC_Skew_UB", "MC_Skew_LB",
                        "Table_Type"
                    ]
                elif type_info in ['hold', 'mpw']:
                    header = [
                        "Arc", "Cell_Name", "output_pin", "rel_pin", "output_pin_dir", "rel_pin_dir", "when", "first_index", "sec_index",
                        "MC_Nominal", "MC_Late_Sigma", "MC_Late_Sigma_UB", "MC_Late_Sigma_LB",
                        "Table_Type"
                    ]
                csv_writer.writerow(header)
                header_written = True
 
            if type_info in ['delay', 'slew']:
                arc_name = parse_fmc_log(folder_path, file_name, csv_writer, log, node, corner, type_info)
            elif type_info in ['hold', 'mpw']:
                arc_name = parse_summary_csv(folder_path, file_name, csv_writer, log, node, corner, type_info, done_list, missing_arcs)
 
            if arc_name is None:
                missing_arcs.append(file_name)
 
        print(f"Completed with {len(done_list)} arcs processed and {len(missing_arcs)} arcs missing.", file=log)
        print("Done arcs:", ', '.join(done_list), file=log)
        print("Missing arcs:", ', '.join(missing_arcs), file=log)
 
if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python script.py <folder_path> <node> <corner> <type_info>")
        sys.exit(1)
 
    folder_path = sys.argv[1]
    node = sys.argv[2]
    corner = sys.argv[3]
    type_info = sys.argv[4]
 
    main(node, corner, folder_path, type_info)
 
