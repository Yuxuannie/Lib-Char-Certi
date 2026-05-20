import os
import sys
import argparse
import csv
import glob
import pandas as pd
import logging
import time
import re
from datetime import datetime

####################################################################
#                         LOGGING SETUP
####################################################################

def setup_logging(log_file=None):
    """Set up logging configuration."""
    logger = logging.getLogger('MC_Golden_Parser')
    logger.setLevel(logging.DEBUG)

    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Create file handler if log file is provided
    if log_file:
        file_handler = logging.FileHandler(log_file, mode='a')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

####################################################################
#                         ARGUMENT PARSING
####################################################################

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Parse MC golden data')
    parser.add_argument('--corner', required=True, help='Corner to process')
    parser.add_argument('--type', required=True, choices=['delay', 'slew'],
                        help='Data type to extract (delay or slew)')
    parser.add_argument('--deck_path', required=True, help='Path to deck folders')
    parser.add_argument('--output_file', required=True, help='Output CSV file path')
    parser.add_argument('--log_file', help='Log file path')
    return parser.parse_args()

####################################################################
#                         ROW DEFINITION HELPERS
####################################################################

def get_row_patterns():
    """Return the patterns for rows we care about and their corresponding output names."""
    # Define the rows we're interested in with their output names
    # We include exact formats based on observed data
    # The output_name is how it should appear in the final CSV
    rows_of_interest = [
        {"patterns": ["Nominal"], "output_name": "Nominal"},
        {"patterns": ["Mean_CI(2.5%)"], "output_name": "Mean_CI(2.5%)"},
        {"patterns": ["Mean"], "output_name": "Mean"},
        {"patterns": ["Mean_CI(97.5%)"], "output_name": "Mean_CI(97.5%)"},
        {"patterns": ["StdDev_CI(2.5%)"], "output_name": "StdDev_CI(2.5%)"},
        {"patterns": ["StdDev"], "output_name": "StdDev"},
        {"patterns": ["StdDev_CI(97.5%)"], "output_name": "StdDev_CI(97.5%)"},
        {"patterns": ["Skewness_CI(2.5%)"], "output_name": "Skewness_CI(2.5%)"},
        {"patterns": ["Skewness"], "output_name": "Skewness"},
        {"patterns": ["Skewness_CI(97.5%)"], "output_name": "Skewness_CI(97.5%)"},

        # Exact pattern formats from observed data
        # Use actual row identifiers from the file with correct comma placement
        {"patterns": ["Q1.35e-01", "Q1.35e-01,(,2.5%)"], "output_name": "Q1.35e-01(2.5%)"},
        {"patterns": ["Q1.35e-01,(,-3)"], "output_name": "Q1.35e-01(-3)"},
        {"patterns": ["Q1.35e-01,(,97.5%)"], "output_name": "Q1.35e-01(97.5%)"},
        {"patterns": ["Q99.865,(,2.5%)"], "output_name": "Q99.865(2.5%)"},
        {"patterns": ["Q99.865,(,3)"], "output_name": "Q99.865(3)"},
        {"patterns": ["Q99.865,(,97.5%)"], "output_name": "Q99.865(97.5%)"}
    ]

    return rows_of_interest

####################################################################
#                         VALUE CONVERSION HELPERS
####################################################################

def convert_to_ps(value, parameter_name, logger):
    """Convert value to picoseconds (multiply by 1e12) for all except skewness."""
    try:
        # Check if we should skip conversion (skewness parameters)
        if parameter_name.startswith("Skewness"):
            return value

        # Convert to float, multiply by 1e12, then back to string
        float_value = float(value)
        ps_value = float_value * 1e12
        logger.debug(f"Converted {parameter_name}: {value} to {ps_value} ps")
        return str(ps_value)
    except ValueError:
        logger.warning(f"Could not convert {parameter_name} value '{value}' to float")
        return value
    except Exception as e:
        logger.error(f"Error converting {value} to ps: {e}")
        return value

def convert_spice_value_to_ps(value_str, logger):
    """
    Convert SPICE time value to picoseconds.
    Handles suffixes like 'n' (nano), 'p' (pico), 'u' (micro), etc.
    """
    try:
        # Clean the value string (remove quotes and spaces)
        value_str = value_str.strip().strip('"').strip("'")

        # Regular expression to extract number and unit
        match = re.match(r'([\d.eE+-]+)([a-zA-Z]*)', value_str)

        if not match:
            logger.warning(f"Could not parse SPICE value: {value_str}")
            return value_str

        number_str, unit = match.groups()
        number = float(number_str)

        # Convert to picoseconds based on unit
        if unit == 'p' or unit == '':  # picoseconds or no unit
            result = number
        elif unit == 'n':  # nanoseconds
            result = number * 1000
        elif unit == 'u':  # microseconds
            result = number * 1e6
        elif unit == 'm':  # milliseconds
            result = number * 1e9
        elif unit == 'f':  # femtoseconds
            result = number * 0.001
        else:
            logger.warning(f"Unknown unit '{unit}' in SPICE value: {value_str}")
            return value_str

        logger.debug(f"Converted SPICE value {value_str} to {result} ps")
        return str(result)

    except Exception as e:
        logger.error(f"Error converting SPICE value '{value_str}' to ps: {e}")
        return value_str

####################################################################
#                         FILE PARSING HELPERS
####################################################################

def extract_rel_pin_slew(netlist_file, logger):
    """Extract the rel_pin_slew parameter from the netlist_params.txt file."""
    try:
        if not os.path.isfile(netlist_file):
            logger.warning(f"netlist_params.txt not found: {netlist_file}")
            return None

        with open(netlist_file, 'r') as f:
            for line in f:
                # Look for the line starting with .param rel_pin_slew
                if line.strip().startswith('.param rel_pin_slew'):
                    logger.debug(f"Found rel_pin_slew line: {line.strip()}")

                    # Extract the value using regex - looking for quoted value
                    match = re.search(r'rel_pin_slew\s*=\s*[\'"]([^\'"]*)[\'"]\s*$', line)
                    if match:
                        raw_value = match.group(1)
                        logger.debug(f"Extracted raw rel_pin_slew value: {raw_value}")

                        # Convert to picoseconds
                        ps_value = convert_spice_value_to_ps(raw_value, logger)
                        logger.debug(f"Converted rel_pin_slew to {ps_value} ps")
                        return ps_value
                    else:
                        # Try alternative pattern without quotes
                        match = re.search(r'rel_pin_slew\s*=\s*\$?\s*([\d.eE+-]+[a-zA-Z]*)', line)
                        if match:
                            raw_value = match.group(1)
                            logger.debug(f"Extracted raw rel_pin_slew value (alt pattern): {raw_value}")

                            # Convert to picoseconds
                            ps_value = convert_spice_value_to_ps(raw_value, logger)
                            logger.debug(f"Converted rel_pin_slew to {ps_value} ps")
                            return ps_value
                        else:
                            logger.warning(f"Could not extract rel_pin_slew value from: {line.strip()}")
                            return None

            logger.warning(f"rel_pin_slew parameter not found in {netlist_file}")
            return None

    except Exception as e:
        logger.error(f"Error extracting rel_pin_slew from {netlist_file}: {e}")
        return None

def check_netlist_params(subdir_path, logger):
    """Check if netlist_params.txt exists and extract rel_pin_slew value."""
    netlist_file = os.path.join(subdir_path, 'netlist_params.txt')
    if os.path.isfile(netlist_file):
        try:
            file_size = os.path.getsize(netlist_file)
            logger.debug(f"netlist_params.txt found: {netlist_file} (Size: {file_size} bytes)")

            # Extract rel_pin_slew parameter
            rel_pin_slew = extract_rel_pin_slew(netlist_file, logger)

            return rel_pin_slew
        except Exception as e:
            logger.warning(f"Error reading netlist_params.txt: {e}")
            return None
    else:
        logger.warning(f"netlist_params.txt not found in {subdir_path}")
        return None

####################################################################
#                         TABLE TYPE DETERMINATION HELPERS
####################################################################

def determine_table_type(arc_name, data_type, logger):
    """
    Determine the table_type based on the arc name and data type.

    For type 'delay':
    - If 4th part is 'rise' -> cell_rise
    - If 4th part is 'fall' -> cell_fall

    For type 'slew':
    - If 4th part is 'rise' -> rise_transition
    - If 4th part is 'fall' -> fall_transition
    """
    try:
        # Split the arc name by underscore
        parts = arc_name.split('_')

        # Check if there are enough parts
        if len(parts) < 4:
            logger.warning(f"Arc name '{arc_name}' doesn't have enough parts to determine table_type")
            return "unknown"

        # Get the 4th part (index 3, since we start from 0)
        fourth_part = parts[3].lower()

        # Determine table_type based on data_type and fourth_part
        if data_type == 'delay':
            if fourth_part == 'rise':
                return "cell_rise"
            elif fourth_part == 'fall':
                return "cell_fall"
            else:
                logger.warning(f"Unknown rise/fall indicator '{fourth_part}' in arc name '{arc_name}'")
                return "unknown_delay"

        elif data_type == 'slew':
            if fourth_part == 'rise':
                return "rise_transition"
            elif fourth_part == 'fall':
                return "fall_transition"
            else:
                logger.warning(f"Unknown rise/fall indicator '{fourth_part}' in arc name '{arc_name}'")
                return "unknown_slew"

        # Shouldn't reach here due to type validation, but just in case
        logger.warning(f"Unknown data_type '{data_type}' for determining table_type")
        return "unknown"

    except Exception as e:
        logger.error(f"Error determining table_type from arc name '{arc_name}': {e}")
        return "error"

####################################################################
#                         MAIN DATA PROCESSING FUNCTION
####################################################################

def process_corner(corner, data_type, deck_path, output_file, logger):
    """Process data for a specific corner and type."""
    start_time = time.time()
    logger.info(f"Starting to process {corner} for {data_type}...")

    #-------------------------------------------
    # Setup and initialization
    #-------------------------------------------

    # Determine column index based on type
    col_idx = 2 if data_type == 'delay' else 3  # 3rd column for delay, 4th for slew
    col_name = "meas_delay" if data_type == 'delay' else "meas_tt_out"
    logger.debug(f"Using column index {col_idx} ({col_name}) for {data_type}")

    # Get row patterns
    row_patterns = get_row_patterns()
    logger.debug(f"Row patterns to extract: {[p['patterns'][0] for p in row_patterns]}")

    # Create output dataframe
    output_data = []

    #-------------------------------------------
    # Path validation
    #-------------------------------------------

    # Path to corner directory
    corner_path = os.path.join(deck_path, corner)
    logger.info(f"Looking for subdirectories in: {corner_path}")

    # Check if corner directory exists
    if not os.path.isdir(corner_path):
        logger.error(f"Corner directory not found: {corner_path}")
        return

    #-------------------------------------------
    # Subdirectory discovery
    #-------------------------------------------

    # Get all subdirectories
    try:
        subdirs = [d for d in os.listdir(corner_path) if os.path.isdir(os.path.join(corner_path, d))]
        logger.info(f"Found {len(subdirs)} subdirectories to process")
        logger.debug(f"Subdirectories: {subdirs[:5]}... (showing first 5)")
    except Exception as e:
        logger.error(f"Error listing subdirectories in {corner_path}: {e}")
        return

    #-------------------------------------------
    # Process each subdirectory
    #-------------------------------------------

    processed_count = 0
    error_count = 0
    for subdir_idx, subdir in enumerate(subdirs):
        subdir_path = os.path.join(corner_path, subdir)
        stats_file = os.path.join(subdir_path, 'stats.csv')
        netlist_file = os.path.join(subdir_path, 'netlist_params.txt')

        logger.debug(f"Processing subdirectory {subdir_idx+1}/{len(subdirs)}: {subdir}")

        # Extract rel_pin_slew from netlist_params.txt
        rel_pin_slew = check_netlist_params(subdir_path, logger)

        # Determine table_type based on arc name and data type
        table_type = determine_table_type(subdir, data_type, logger)
        logger.debug(f"Determined table_type: {table_type} for arc {subdir}")

        # Check if stats.csv exists
        if not os.path.isfile(stats_file):
            logger.warning(f"stats.csv not found in {subdir_path}")
            error_count += 1
            continue

        # Read stats.csv
        try:
            logger.debug(f"Reading stats.csv: {stats_file}")
            with open(stats_file, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)

            # Debug header information
            if rows and len(rows) > 0:
                logger.debug(f"Header row: {rows[0]}")

            # Ensure there are enough rows
            if len(rows) < 20:  # Header + 19 data rows minimum
                logger.warning(f"Incomplete data in {stats_file} - only {len(rows)} rows found")
                error_count += 1
                continue

            # Debug: Print first few rows to see what's actually in the file
            # logger.debug(f"First few rows in {stats_file}:")
            # row_count = min(len(rows), 30)  # Limit to first 30 rows
            # for i, row in enumerate(rows[:row_count]):
            #     if row and len(row) > 0:
            #         try:
            #             logger.debug(f"  Row {i}: '{row[0]}' -> {row[col_idx] if len(row) > col_idx else 'N/A'}")
            #         except:
            #             logger.debug(f"  Row {i}: Error reading row")

            # Extract values for rows of interest
            row_data = {
                'Arc': subdir,
                'rel_pin_slew': rel_pin_slew if rel_pin_slew is not None else "N/A",
                'Table_type': table_type
            }
            logger.debug(f"Extracting data for Arc: {subdir}, rel_pin_slew: {rel_pin_slew}, Table_type: {table_type}")

            # Iterate through each row of interest
            for row_info in row_patterns:
                output_name = row_info["output_name"]
                patterns = row_info["patterns"]

                try:
                    # Try to match any of the patterns exactly
                    row_found = False
                    for pattern in patterns:
                        for row in rows:
                            # For quantile rows (starting with Q), match the full pattern before the last three values
                            if pattern.startswith("Q") and len(row) >= 3:
                                # Check if the row starts with the pattern (split by comma and check first parts)
                                row_start = ','.join(row[:-3])  # Join all parts except the last three values

                                if pattern in row_start:
                                    # For percentile rows, use the correct column from the end
                                    if data_type == 'delay':
                                        # Use second-to-last column for delay (meas_delay)
                                        col_to_use = -2
                                    else:
                                        # Use last column for slew (meas_tt_out)
                                        col_to_use = -1
                                    raw_value = row[col_to_use]
                                    value = convert_to_ps(raw_value, output_name, logger)
                                    row_data[output_name] = value
                                    logger.debug(f"  Quantile match: {pattern} in {row_start} -> {output_name}: {raw_value} -> {value}")
                                    row_found = True
                                    break
                            # For standard statistic rows, just match the first column
                            elif len(row) > 0 and row[0] == pattern:
                                raw_value = row[col_idx] if len(row) > col_idx else "N/A"
                                value = convert_to_ps(raw_value, output_name, logger)
                                row_data[output_name] = value
                                logger.debug(f"  Exact match: {pattern} -> {output_name}: {raw_value} -> {value}")
                                row_found = True
                                break

                        if row_found:
                            break

                    # If no match was found, mark as N/A but continue processing
                    if not row_found:
                        row_data[output_name] = "N/A"
                        logger.warning(f"Could not find row matching any pattern for '{output_name}' in {stats_file}")

                except Exception as e:
                    error_msg = f"Error extracting for '{output_name}' from {stats_file}: {e}"
                    logger.warning(error_msg)
                    row_data[output_name] = "N/A"

            output_data.append(row_data)
            processed_count += 1

            # Log progress for every 10% of subdirectories processed
            if processed_count % max(1, len(subdirs) // 10) == 0:
                logger.info(f"Progress: {processed_count}/{len(subdirs)} ({processed_count/len(subdirs):.1%})")

        except Exception as e:
            logger.error(f"Error processing {stats_file}: {e}")
            error_count += 1

    #-------------------------------------------
    # Create and save output
    #-------------------------------------------

    # Create DataFrame from collected data
    if output_data:
        logger.info(f"Creating DataFrame with {len(output_data)} rows")
        df = pd.DataFrame(output_data)

        # Log summary statistics
        logger.debug(f"DataFrame shape: {df.shape}")
        logger.debug(f"DataFrame columns: {df.columns.tolist()}")

        # Reorganize columns - Arc, rel_pin_slew as first two, Table_type as last
        if set(['Arc', 'rel_pin_slew', 'Table_type']).issubset(df.columns):
            other_cols = [col for col in df.columns if col not in ['Arc', 'rel_pin_slew', 'Table_type']]
            col_order = ['Arc', 'rel_pin_slew'] + other_cols + ['Table_type']
            df = df[col_order]
            logger.debug(f"Reordered columns: {df.columns.tolist()}")

        # Save to CSV
        try:
            logger.info(f"Saving data to {output_file}")
            df.to_csv(output_file, index=False)
            logger.info(f"Successfully saved data to {output_file}")
        except Exception as e:
            logger.error(f"Error saving data to {output_file}: {e}")
    else:
        logger.warning(f"No data found for {corner} {data_type}")

    #-------------------------------------------
    # Processing summary
    #-------------------------------------------

    end_time = time.time()
    elapsed_time = end_time - start_time
    logger.info(f"Processing summary for {corner} {data_type}:")
    logger.info(f"  - Total subdirectories: {len(subdirs)}")
    logger.info(f"  - Successfully processed: {processed_count}")
    logger.info(f"  - Errors encountered: {error_count}")
    logger.info(f"  - Processing time: {elapsed_time:.2f} seconds")

####################################################################
#                         MAIN FUNCTION
####################################################################

def main():
    """Main function."""
    #-------------------------------------------
    # Initialization and setup
    #-------------------------------------------

    # Parse arguments
    args = parse_args()

    # Set up logging
    logger = setup_logging(args.log_file)

    logger.info("="*50)
    logger.info(f"MC Golden Data Parser - Started at {datetime.now()}")
    logger.info(f"Python Version: {sys.version}")
    logger.info(f"Command line args: {args}")

    #-------------------------------------------
    # Path validation
    #-------------------------------------------

    if not os.path.isdir(args.deck_path):
        logger.error(f"Deck path does not exist: {args.deck_path}")
        return 1

    output_dir = os.path.dirname(args.output_file)
    if output_dir and not os.path.isdir(output_dir):
        logger.warning(f"Output directory does not exist: {output_dir}")
        try:
            logger.info(f"Creating output directory: {output_dir}")
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create output directory: {e}")
            return 1

    #-------------------------------------------
    # Main processing
    #-------------------------------------------

    try:
        process_corner(args.corner, args.type, args.deck_path, args.output_file, logger)
        logger.info(f"MC Golden Data Parser - Completed at {datetime.now()}")
        return 0
    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        return 1

####################################################################
#                         ENTRY POINT
####################################################################

if __name__ == "__main__":
    sys.exit(main())
