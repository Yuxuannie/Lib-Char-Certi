#!/usr/bin/env python3
 
import sys
import re
import os
import csv
import traceback
from datetime import datetime
 
# Debug log function
def debug_log(message):
    """Print debug message with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[DEBUG {timestamp}] {message}")
 
def parse_mc_sim(file_path):
    """
    Parse mc_sim.sp file to extract:
    1. Content from second line to *TEMPLATE_DECK
    2. Line with .param cl
    3. Line with .param rel_pin_slew
    """
    debug_log(f"Starting to parse mc_sim file: {file_path}")
    results = []
   
    try:
        with open(file_path, 'r') as file:
            debug_log(f"Successfully opened file: {file_path}")
            lines = file.readlines()
            debug_log(f"Read {len(lines)} lines from file")
           
            # Extract content from second line to *TEMPLATE_DECK
            if len(lines) > 1:
                template_index = -1
                for i, line in enumerate(lines):
                    if '* TEMPLATE_DECK' in line:
                        template_index = i
                        debug_log(f"Found * TEMPLATE_DECK at line {i}")
                        break
               
                if template_index > 1:  # Make sure we found * TEMPLATE_DECK
                    header_content = ''.join(lines[1:template_index]).strip()
                    debug_log(f"Extracted header content from line 2 to line {template_index}")
                    results.append(header_content)
                else:
                    debug_log("WARNING: Could not find * TEMPLATE_DECK marker")
                    results.append("")  # Empty string if not found
            else:
                debug_log("WARNING: File has less than 2 lines")
           
            # Find lines with specific parameters
            cl_line = ""
            rel_pin_slew_line = ""
           
            for i, line in enumerate(lines):
                if line.strip().startswith(".param cl "):
                    cl_line = line.strip()
                    debug_log(f"Found .param cl at line {i+1}: {cl_line}")
                elif line.strip().startswith(".param rel_pin_slew"):
                    rel_pin_slew_line = line.strip()
                    debug_log(f"Found .param rel_pin_slew at line {i+1}: {rel_pin_slew_line}")
           
            if not cl_line:
                debug_log("WARNING: .param cl not found in the file")
           
            if not rel_pin_slew_line:
                debug_log("WARNING: .param rel_pin_slew not found in the file")
           
            results.append(cl_line)
            results.append(rel_pin_slew_line)
       
        debug_log(f"Completed parsing mc_sim file with {sum(1 for r in results if r)} successful extractions")
        return results
    except Exception as e:
        debug_log(f"ERROR parsing mc_sim.sp: {str(e)}")
        debug_log(traceback.format_exc())
        return ["", "", ""]
 
def parse_ava_report(file_path):
    """
    Parse OUT.ava.report to extract the moments table between
    "#95% Bootstrap confidence intervals for moments based on 500 re-samples" and "##Response_Correlation_Matrix"
    """
    debug_log(f"Starting to parse ava report file: {file_path}")
    debug_log("Note: Changed end pattern to '##Response_Correlation_Matrix'")
    try:
        with open(file_path, 'r') as file:
            debug_log(f"Successfully opened file: {file_path}")
            content = file.read()
            debug_log(f"Read {len(content)} characters from file")
           
            # Define the start and end patterns
            start_pattern = "##Sample_Moments"
            end_pattern = "##Response_Correlation_Matrix"
           
            # Extract the section
            start_idx = content.find(start_pattern)
            if start_idx == -1:
                debug_log(f"ERROR: Start pattern not found: '{start_pattern}'")
                return []
            else:
                debug_log(f"Found start pattern at position {start_idx}")
               
            # Find the end_pattern after the start_pattern
            end_idx = content.find(end_pattern, start_idx)
            if end_idx == -1:
                debug_log(f"ERROR: End pattern not found: '{end_pattern}'")
                return []
            else:
                debug_log(f"Found end pattern at position {end_idx}")
               
            section = content[start_idx:end_idx].strip()
            debug_log(f"Extracted section of {len(section)} characters")
           
            # Process the moments and quantiles tables to extract data
            lines = section.split('\n')
            debug_log(f"Split section into {len(lines)} lines")
           
            results = []
            moments_table_found = False
            quantiles_table_found = False
            header_idx = -1
 
            for i, line in enumerate(lines):
                if "half_tt_out" in line and "meas_delay" in line and "meas_tt_out" in line:
                    if not moments_table_found:
                        header_idx = i
                        moments_table_found = True
                        debug_log(f"Found moments table header line at index {i}: {line}")
                    else:
                        quantiles_table_found = True
                        header_idx = i
                        debug_log(f"Found quantiles table header line at index {i}: {line}")
                    break
 
            if not moments_table_found:
                debug_log("ERROR: Could not find header line with required columns for moments table")
                return []
 
            # Process table data for both moments and quantiles
            table_data = []
            if moments_table_found:
                table_data = extract_table_data(lines, header_idx)
            if quantiles_table_found:
                table_data += extract_quantiles_data(lines, header_idx)
 
            debug_log(f"Total parsed rows: {len(table_data)}")
            return table_data
                 
    except Exception as e:
        debug_log(f"ERROR parsing OUT.ava.report: {str(e)}")
        debug_log(traceback.format_exc())
        return []
 
def extract_table_data(lines, header_idx):
    """
    Extract and format data from table section starting at header_idx.
    """
    results = []
    header_cols = [col for col in re.split(r'\s+', lines[header_idx].strip()) if col]
    debug_log(f"Original header columns: {header_cols}")
 
    formatted_header = [""]
    for col in header_cols:
        if col in ["half_tt_out", "meas_delay", "meas_tt_out"]:
            formatted_header.append(col)
 
    debug_log(f"Formatted header with empty first column: {formatted_header}")
    results.append(formatted_header)
 
    data_rows = 0
    for i in range(header_idx + 1, len(lines)):
        line = lines[i].strip()
        if not line or line.startswith('#'):
            continue
 
        columns = [col for col in re.split(r'\s+', line) if col]
        if not columns:
            continue
 
        row_data = [columns[0]]
        for j in range(1, len(columns)):
            if j < len(columns):
                row_data.append(columns[j])
 
        debug_log(f"Parsed data row {data_rows+1}: {row_data}")
        results.append(row_data)
        data_rows += 1
 
    debug_log(f"Total parsed: 1 header row + {data_rows} data rows in moments table")
    return results
 
def extract_quantiles_data(lines, header_idx):
    """
    Extract and format data from quantiles section starting at header_idx.
    """
    results = []
    quantiles_header_cols = [col for col in re.split(r'\s+', lines[header_idx].strip()) if col]
    debug_log(f"Quantiles header columns: {quantiles_header_cols}")
 
    formatted_header = [""]
    for col in quantiles_header_cols:
        if col in ["half_tt_out", "meas_delay", "meas_tt_out"]:
            formatted_header.append(col)
 
    debug_log(f"Formatted header with empty first column for quantiles: {formatted_header}")
    results.append(formatted_header)
 
    data_rows = 0
    for i in range(header_idx + 1, len(lines)):
        line = lines[i].strip()
        if not line or line.startswith('#'):
            continue
 
        columns = [col for col in re.split(r'\s+', line) if col]
        if not columns:
            continue
 
        row_data = []
        first_col_end_idx = line.find(')')
        row_data.append(line[:first_col_end_idx + 1])
 
        remaining_cols = [col for col in re.split(r'\s+', line[first_col_end_idx + 1:].strip()) if col]
        row_data += remaining_cols
       
        debug_log(f"Parsed quantiles data row {data_rows+1}: {row_data}")
        results.append(row_data)
        data_rows += 1
 
    debug_log(f"Total parsed: 1 header row + {data_rows} data rows in quantiles table")
    return results
 
def main():
    debug_log("=" * 50)
    debug_log("Starting MC data parsing script")
   
    if len(sys.argv) != 7:
        debug_log(f"ERROR: Incorrect number of arguments. Got {len(sys.argv)-1}, expected 6")
        print("Usage: python parse_mc_data.py <mc_sim.sp> <OUT.ava.report> <csv_output> <txt_output> <arc_name> <corner_name>")
        sys.exit(1)
       
    mc_sim_file = sys.argv[1]
    report_file = sys.argv[2]
    csv_output = sys.argv[3]
    txt_output = sys.argv[4]
    arc_name = sys.argv[5]
    corner_name = sys.argv[6]
   
    debug_log(f"Arguments:")
    debug_log(f"  mc_sim_file: {mc_sim_file}")
    debug_log(f"  report_file: {report_file}")
    debug_log(f"  csv_output: {csv_output}")
    debug_log(f"  txt_output: {txt_output}")
    debug_log(f"  arc_name: {arc_name}")
    debug_log(f"  corner_name: {corner_name}")
   
    # Check if input files exist
    if not os.path.exists(mc_sim_file):
        debug_log(f"ERROR: mc_sim file does not exist: {mc_sim_file}")
        sys.exit(1)
   
    if not os.path.exists(report_file):
        debug_log(f"ERROR: report file does not exist: {report_file}")
        sys.exit(1)
   
    # Parse mc_sim.sp
    debug_log("Calling parse_mc_sim function")
    mc_sim_results = parse_mc_sim(mc_sim_file)
    debug_log(f"Got {len(mc_sim_results)} results from mc_sim parse")
   
    # Parse OUT.ava.report
    debug_log("Calling parse_ava_report function")
    ava_results = parse_ava_report(report_file)
    debug_log(f"Got {len(ava_results)} rows from ava_report parse")
   
    # Create output directories if they don't exist
    os.makedirs(os.path.dirname(txt_output), exist_ok=True)
    os.makedirs(os.path.dirname(csv_output), exist_ok=True)
   
    # Write to TXT file (write mode, not append, since we have a file per arc now)
    debug_log(f"Writing to TXT file: {txt_output}")
    try:
        with open(txt_output, 'w') as txt_file:
            txt_file.write(f"// ARC: {arc_name} - CORNER: {corner_name}\n")
            for i, result in enumerate(mc_sim_results):
                if result:  # Only write non-empty results
                    debug_log(f"Writing result {i+1} to TXT file ({len(result)} characters)")
                    txt_file.write(f"{result}\n")
                else:
                    debug_log(f"Skipping empty result {i+1}")
            txt_file.write("\n")
        debug_log("Successfully wrote TXT file")
    except Exception as e:
        debug_log(f"ERROR writing TXT file: {str(e)}")
        debug_log(traceback.format_exc())
   
    # Write to CSV file exactly as it appears in the original file
    if ava_results:
        debug_log(f"Writing to CSV file: {csv_output}")
        try:
            with open(csv_output, 'w', newline='') as csv_file:
                writer = csv.writer(csv_file)
                # Write all rows directly from the parsed results
                for i, row in enumerate(ava_results):
                    debug_log(f"Writing row {i+1} to CSV: {row}")
                    writer.writerow(row)
            debug_log("Successfully wrote CSV file")
        except Exception as e:
            debug_log(f"ERROR writing CSV file: {str(e)}")
            debug_log(traceback.format_exc())
    else:
        debug_log("No ava_results to write to CSV")
   
    debug_log("Script completed successfully")
    debug_log("=" * 50)
 
if __name__ == "__main__":
    main()
 
