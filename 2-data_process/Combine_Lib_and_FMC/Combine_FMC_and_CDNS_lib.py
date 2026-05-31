import ldbx
import re
import os
import numpy as np
import pandas as pd
from argparse import ArgumentParser
 
"""
Enhanced script to add library values from characterization to compare with FMC golden data.
Added rel_pin_slew extraction for sigma pass rate calculations.
 
Input Columns:
Cell_Name, Arc, Index, MC_Nominal, MC_Early_Sigma, MC_Early_Sigma_UB, MC_Early_Sigma_LB, MC_Late_Sigma, MC_Late_Sigma_UB
MC_Late_Sigma_LB, MC_Std, MC_Std_UB, MC_Std_LB, MC_Skew, MC_Skew_UB, MC_Skew_LB, MC_Meansht, MC_Meansht_UB, MC_Meansht_LB, Table_Type
 
Enhanced Output Columns:
Added rel_pin_slew column for sigma processing (formatted to 1 decimal place)
 
Modifications and Updates:
1/10/2025 - Original version 
1/20/2025 - Different handling for Delay, Slew and Hold
[Current] - Added rel_pin_slew extraction:
  - Unit_change = 1 (CDNS already uses ps)
  - Delay/Slew: 8x8 tables, rel_pin_slew from index_1 using fir_index
  - Hold: 5x5 tables, rel_pin_slew from index_2 using sec_index
  - rel_pin_slew formatted to 1 decimal place
 
Owner: Yuxuan Nie
"""
 
def get_cell_names(lib):
    """ Function used to get all cell names from given library"""
    all_ref_cell_groups = lib.getChildren()
    all_cell_names = set()
    for each_cell in all_ref_cell_groups:
        if each_cell.getHeader() == "cell":
            each_cell_name = each_cell.getName()
            all_cell_names.add(each_cell_name)
    return all_cell_names
 
def parse_arc_info(arc_info, mode):
    """ Function used to get all arc information one by one for ldbx reading"""
    arc_parts = arc_info.split("_")
    # Read arc parts from a long string: combinational_MUXANDHLNXROP7BUP13QNHPM3P4GCF0_Z_rise_S1_rise_notI0_notI1_notI2_I3_S0_4_4
    timing_type = arc_parts[0]
    cell_name = arc_parts[1]
    out_pin = arc_parts[2]
    out_pin_direction = arc_parts[3]
    rel_pin = arc_parts[4]
    rel_pin_direction = arc_parts[5]
    when_condition = arc_parts[6:][:-2]  # This is parts like : ['notA1', 'notB1', 'B2', 'C1', 'notC2']
 
    fir_index = int(float(arc_parts[-2])-1)
    sec_index = int(float(arc_parts[-1])-1)
    when_poss = 'None'
 
    if when_condition[0] == 'NO' and when_condition[1] == 'CONDITION':
        when = 'NO_CONDITION'
    else:
        replaced_list = [item.replace('not', '!') for item in when_condition]
        when = '&'.join(replaced_list)
        when_poss = '&&'.join(replaced_list)  # Sometimes A2&A3&!B1&B2&!B3 is replaced in lib by A2&&A3&&!B1&&B2&&!B3
 
    return cell_name, out_pin, rel_pin, when, when_poss, fir_index, sec_index
 
def get_tbl_point(each_tim_group, target_tbl, fir_index, sec_index, shape=8):
    """ Function used to get table point from ldbx timing group"""
    tbl_grp = each_tim_group.getChildren(target_tbl)
    tbl_obj = tbl_grp[0].getTable()
    tbl_value = tbl_obj.getValue()
    tbl_value_reshape = np.reshape(np.array(tbl_value), (shape, shape))
    target_value = tbl_value_reshape[fir_index, sec_index]
    target_value = float(target_value)*unit_change
 
    return target_value
 
def get_rel_pin_slew(each_tim_group, target_tbl, fir_index, sec_index, shape=8, mode='Delay'):
    """
    Enhanced function to extract rel_pin_slew value from table
    For Delay/Slew: rel_pin_slew is index_1 (first dimension)
    For Hold: rel_pin_slew is index_2 (second dimension) and use sec_index
    Returns the rel_pin_slew value formatted to 1 decimal place
    """
    try:
        tbl_grp = each_tim_group.getChildren(target_tbl)
        if len(tbl_grp) == 0:
            print(f"Warning: No table group found for {target_tbl}")
            return None
 
        tbl_obj = tbl_grp[0].getTable()
        if tbl_obj.isEmpty():
            print(f"Warning: Empty table for {target_tbl}")
            return None
 
        # Get indices
        indices = tbl_obj.getIndices()
        if len(indices) < 2:
            print(f"Warning: Insufficient indices found for {target_tbl}")
            return None
 
        # Select correct index based on mode
        if mode == 'Hold':
            # For Hold: rel_pin_slew is index_2, use sec_index
            if sec_index >= len(indices[1]):
                print(f"Warning: sec_index {sec_index} out of bounds for index_2 length {len(indices[1])}")
                return None
            rel_pin_slew = float(indices[1][sec_index]) * unit_change
        else:
            # For Delay/Slew: rel_pin_slew is index_1, use fir_index
            if fir_index >= len(indices[0]):
                print(f"Warning: fir_index {fir_index} out of bounds for index_1 length {len(indices[0])}")
                return None
            rel_pin_slew = float(indices[0][fir_index]) * unit_change
 
        # Format to 1 decimal place
        return round(rel_pin_slew, 1)
 
    except Exception as e:
        print(f"Error extracting rel_pin_slew from {target_tbl}: {e}")
        return None
 
def get_tbl_and_slew_point(each_tim_group, target_tbl, fir_index, sec_index, shape=8, mode='Delay'):
    """
    Enhanced function that gets both table value and rel_pin_slew
    For Delay/Slew: rel_pin_slew is index_1, use fir_index
    For Hold: rel_pin_slew is index_2, use sec_index
    Returns tuple: (table_value, rel_pin_slew formatted to 1 decimal)
    """
    try:
        tbl_grp = each_tim_group.getChildren(target_tbl)
        if len(tbl_grp) == 0:
            return None, None
 
        tbl_obj = tbl_grp[0].getTable()
        if tbl_obj.isEmpty():
            return None, None
 
        # Get table value
        tbl_value = tbl_obj.getValue()
        tbl_value_reshape = np.reshape(np.array(tbl_value), (shape, shape))
        target_value = float(tbl_value_reshape[fir_index, sec_index]) * unit_change
 
        # Get rel_pin_slew based on mode
        indices = tbl_obj.getIndices()
        if len(indices) >= 2:
            if mode == 'Hold':
                # For Hold: rel_pin_slew is index_2, use sec_index
                if sec_index < len(indices[1]):
                    rel_pin_slew = round(float(indices[1][sec_index]) * unit_change, 1)
                else:
                    rel_pin_slew = None
            else:
                # For Delay/Slew: rel_pin_slew is index_1, use fir_index
                if fir_index < len(indices[0]):
                    rel_pin_slew = round(float(indices[0][fir_index]) * unit_change, 1)
                else:
                    rel_pin_slew = None
        else:
            rel_pin_slew = None
 
        return target_value, rel_pin_slew
 
    except Exception as e:
        print(f"Error extracting table value and slew from {target_tbl}: {e}")
        return None, None
 
parser = ArgumentParser()
parser.add_argument("-lib_path", help="Input library path and filename", dest="input_libpath", default=None)
parser.add_argument("-txt_path", help="Input txt path with value columns", dest="input_txtpath", default=None)
parser.add_argument("-nominal_check", help="Boolean flag (True or False): If present means Nominal is needed to compare, else ignore", action='store_true')
parser.add_argument("-mode", choices=['Delay', 'Slew', 'Hold'], help="Select a Data Type: Delay, Slew, Hold", dest="mode", required=True)
 
unit_change = 1  # cdns libs are already in picoseconds
args = parser.parse_args()
lib_file_path = args.input_libpath
txt_file_path = args.input_txtpath
base_name = os.path.basename(txt_file_path)
basename_noext = os.path.splitext(base_name)[0]
 
if not os.path.exists(txt_file_path) or not os.path.isfile(txt_file_path):
    print(f"Error: Text report file {txt_file_path} not found!")
elif not os.path.exists(lib_file_path) or not os.path.isfile(lib_file_path):
    print(f"Error: Library file {lib_file_path} not found!")
else:
    # Read FMC data
    fmc_txt = np.genfromtxt(txt_file_path, delimiter=',', dtype=None, encoding='utf-8')
    header = fmc_txt[0, :]
    fmc_txt_df = pd.DataFrame(fmc_txt[1:, :], columns=header)
    print(f"Reading {txt_file_path} with header {header}, row number is {len(fmc_txt)-1}.")
 
    # Read library
    lib = ldbx.read_db(lib_file_path)
    lib_name = lib.getName()
    print("Reading:", lib_name)
    all_cell_names = get_cell_names(lib)
 
    # Initialize result lists
    arc_found = [False]*(len(fmc_txt)-1)
    lib_nominal, lib_early_sigma, lib_late_sigma, lib_skewness, lib_std_dev, lib_mean_shift = [], [], [], [], [], []
    missing_arcs = []  # FMC golden arcs the lib does not cover (reported, kept NaN, never dropped)
    lookup_debug = []  # per-arc lib-lookup diagnostics (why a lib value ends up 0/NaN)

    for index, row in fmc_txt_df.iterrows():
        arc_info = row['Arc']
        cell_name, out_pin, rel_pin, when, when_poss, fir_index, sec_index = parse_arc_info(arc_info, args.mode)
        table_type = row['Table_Type']
        sigma_table = 'ocv_sigma_' + table_type
        skewness_table = 'ocv_skewness_' + table_type
        std_dev_table = 'ocv_std_dev_' + table_type
        mean_shift_table = 'ocv_mean_shift_' + table_type

        # Per-row lib values default to NaN so an arc the lib does NOT cover stays
        # row-aligned with its MC data (reported + excluded downstream, never dropped).
        r_nominal = r_early = r_late = r_skew = r_std = r_mean = np.nan

        # Start read from library using ldbx
        cell_ok = pin_ok = False
        n_matched = 0
        try:
            cell = lib.getChildren("cell", cell_name)
            cell_ok = bool(cell)
            out_pin_grp = cell[0].getChildren("pin", out_pin)
            pin_ok = bool(out_pin_grp)
            tim_groups = out_pin_grp[0].getChildren("timing")
        except Exception as e:
            print(f"Warning: cell/pin lookup failed for arc {arc_info}: {e}")
            tim_groups = []
        n_timing = len(tim_groups)

        for each_tim_group in tim_groups:
            tim_block_attr = each_tim_group.getAttr()
            rel_pin_attr = None
            when_cond_attr, time_type_attr = 'None', 'None'
            for each_attr_tpl in tim_block_attr:
                if each_attr_tpl[0] == "related_pin":
                    rel_pin_attr = each_attr_tpl[1]
                if each_attr_tpl[0] == "when":
                    when_cond_attr = each_attr_tpl[1]
                if each_attr_tpl[0] == "timing_type":
                    time_type_attr = each_attr_tpl[1]

            matched = (rel_pin_attr == rel_pin) and (when_cond_attr in (when, when_poss, 'None'))

            if args.mode == 'Delay' or args.mode == 'Slew':
                if matched:
                    arc_found[index] = True
                    n_matched += 1

                    sigma_tbl_grp = each_tim_group.getChildren(sigma_table)
                    for each_sigma_tbl in sigma_tbl_grp:
                        tbl_obj = each_sigma_tbl.getTable()
                        tbl_value = tbl_obj.getValue()
                        sigma_type = each_sigma_tbl.getAttr(['sigma_type'])[0][1]
                        tbl_value_reshape = np.reshape(np.array(tbl_value), (8, 8))
                        if sigma_type == 'early':
                            r_early = float(tbl_value_reshape[fir_index, sec_index]) * unit_change
                        elif sigma_type == 'late':
                            r_late = float(tbl_value_reshape[fir_index, sec_index]) * unit_change

                    # 8x8 tables for Delay/Slew (slew extraction removed; abs check no longer used)
                    std_dev_value, _ = get_tbl_and_slew_point(each_tim_group, std_dev_table, fir_index, sec_index, shape=8, mode=args.mode)
                    skewness_value, _ = get_tbl_and_slew_point(each_tim_group, skewness_table, fir_index, sec_index, shape=8, mode=args.mode)
                    mean_shift_value, _ = get_tbl_and_slew_point(each_tim_group, mean_shift_table, fir_index, sec_index, shape=8, mode=args.mode)

                    if std_dev_value is not None and skewness_value is not None and std_dev_value != 0:
                        r_skew = skewness_value / std_dev_value
                        r_std = std_dev_value
                    else:
                        r_skew = 0.0
                        r_std = std_dev_value if std_dev_value is not None else 0.0

                    r_mean = mean_shift_value if mean_shift_value is not None else 0.0

                    if args.nominal_check:
                        nominal_value, _ = get_tbl_and_slew_point(each_tim_group, table_type, fir_index, sec_index, shape=8, mode=args.mode)
                        r_nominal = nominal_value if nominal_value is not None else 0.0

            if args.mode == 'Hold':
                if 'hold_' in time_type_attr and matched:
                    arc_found[index] = True
                    n_matched += 1

                    sigma_tbl_grp = each_tim_group.getChildren(sigma_table)
                    for each_sigma_tbl in sigma_tbl_grp:
                        tbl_obj = each_sigma_tbl.getTable()
                        tbl_value = tbl_obj.getValue()
                        tbl_value_reshape = np.reshape(np.array(tbl_value), (5, 5))
                        r_late = float(tbl_value_reshape[fir_index, sec_index]) * unit_change

                    if args.nominal_check:
                        nominal_value, _ = get_tbl_and_slew_point(each_tim_group, table_type, fir_index, sec_index, shape=5, mode='Hold')
                        r_nominal = nominal_value if nominal_value is not None else 0.0

        # Append exactly once per row so lib lists stay aligned with the MC rows.
        if args.mode == 'Delay' or args.mode == 'Slew':
            lib_early_sigma.append(r_early)
            lib_late_sigma.append(r_late)
            lib_std_dev.append(r_std)
            lib_skewness.append(r_skew)
            lib_mean_shift.append(r_mean)
            if args.nominal_check:
                lib_nominal.append(r_nominal)
        else:  # Hold
            lib_late_sigma.append(r_late)
            if args.nominal_check:
                lib_nominal.append(r_nominal)

        lookup_debug.append({
            'Arc': arc_info, 'cell_found': cell_ok, 'pin_found': pin_ok,
            'n_timing': n_timing, 'n_matched': n_matched,
            'lib_early': r_early, 'lib_late': r_late,
            'when': when, 'fir_index': fir_index, 'sec_index': sec_index,
        })

        if not arc_found[index]:
            missing_arcs.append(arc_info)
            print(f"Warning: Arc {arc_info} not covered by lib (kept as NaN, excluded from pass rate)")
 
# Process results and create output CSV
if args.mode == 'Delay' or args.mode == 'Slew':
    mc_nominal = fmc_txt_df['MC_Nominal'].astype(float)
    mc_early_sigma = fmc_txt_df['MC_Early_Sigma'].astype(float)
    mc_early_sigma_lb = fmc_txt_df['MC_Early_Sigma_LB'].astype(float)
    mc_early_sigma_ub = fmc_txt_df['MC_Early_Sigma_UB'].astype(float)
    mc_late_sigma = fmc_txt_df['MC_Late_Sigma'].astype(float)
    mc_late_sigma_lb = fmc_txt_df['MC_Late_Sigma_LB'].astype(float)
    mc_late_sigma_ub = fmc_txt_df['MC_Late_Sigma_UB'].astype(float)
    mc_std = fmc_txt_df['MC_Std'].astype(float)
    mc_std_lb = fmc_txt_df['MC_Std_LB'].astype(float)
    mc_std_ub = fmc_txt_df['MC_Std_UB'].astype(float)
    mc_skew = fmc_txt_df['MC_Skew'].astype(float)
    mc_skew_lb = fmc_txt_df['MC_Skew_LB'].astype(float)
    mc_skew_ub = fmc_txt_df['MC_Skew_UB'].astype(float)
    mc_mean_shift = fmc_txt_df['MC_Meansht'].astype(float)
    mc_mean_shift_lb = fmc_txt_df['MC_Meansht_LB'].astype(float)
    mc_mean_shift_ub = fmc_txt_df['MC_Meansht_UB'].astype(float)
 
    # Check for missing arcs
    if len(mc_late_sigma) != len(lib_late_sigma):
        false_index = [index for index, value in enumerate(arc_found) if value is False]
        arc_list = fmc_txt_df.iloc[false_index]['Arc']
        print(f"Warning: These Arcs {arc_list} not found")
 
    if args.nominal_check:
        # Put all data into one dataframe and save to a rpt file with expected format (including rel_pin_slew)
        csv_info = {'Cell_Name': fmc_txt_df['Cell_Name'], 'Arc': fmc_txt_df['Arc'],
                    'MC_Nominal': mc_nominal, 'CDNS_Lib_Nominal': lib_nominal,
                    'MC_Early_Sigma': mc_early_sigma, 'CDNS_Lib_Early_Sigma': lib_early_sigma, 'CDNS_Lib_Early_Sigma_Dif': np.array(lib_early_sigma)-mc_early_sigma, 'CDNS_Lib_Early_Sigma_Rel': (np.array(lib_early_sigma)-mc_early_sigma)/mc_early_sigma, 'MC_Early_Sigma_LB': mc_early_sigma_lb, 'MC_Early_Sigma_UB': mc_early_sigma_ub,
                    'MC_Late_Sigma': mc_late_sigma, 'CDNS_Lib_Late_Sigma': lib_late_sigma, 'CDNS_Lib_Late_Sigma_Dif': np.array(lib_late_sigma)-mc_late_sigma, 'CDNS_Lib_Late_Sigma_Rel': (np.array(lib_late_sigma)-mc_late_sigma)/mc_late_sigma, 'MC_Late_Sigma_LB': mc_late_sigma_lb, 'MC_Late_Sigma_UB': mc_late_sigma_ub,
                    'MC_Std': mc_std, 'CDNS_Lib_Std': lib_std_dev, 'CDNS_Lib_Std_Dif': np.array(lib_std_dev)-mc_std, 'CDNS_Lib_Std_Rel': (np.array(lib_std_dev)-mc_std)/mc_std, 'MC_Std_LB': mc_std_lb, 'MC_Std_UB': mc_std_ub,
                    'MC_Skew': mc_skew, 'CDNS_Lib_Skew': lib_skewness, 'CDNS_Lib_Skew_Dif': np.array(lib_skewness)-mc_skew, 'CDNS_Lib_Skew_Rel': (np.array(lib_skewness)-mc_skew)/mc_skew, 'MC_Skew_LB': mc_skew_lb, 'MC_Skew_UB': mc_skew_ub,
                    'MC_Meanshift': mc_mean_shift, 'CDNS_Lib_Meanshift': lib_mean_shift, 'CDNS_Lib_Meanshift_Dif': np.array(lib_mean_shift)-mc_mean_shift, 'CDNS_Lib_Meanshift_Rel': (np.array(lib_mean_shift)-mc_mean_shift)/mc_mean_shift, 'MC_Meanshift_LB': mc_mean_shift_lb, 'MC_Meanshift_UB': mc_mean_shift_ub,
                    'Table_Type': fmc_txt_df['Table_Type']}
    else:
        # Put all data into one dataframe and save to a rpt file with expected format (including rel_pin_slew)
        csv_info = {'Cell_Name': fmc_txt_df['Cell_Name'], 'Arc': fmc_txt_df['Arc'],
                    'MC_Early_Sigma': mc_early_sigma, 'CDNS_Lib_Early_Sigma': lib_early_sigma, 'CDNS_Lib_Early_Sigma_Dif': np.array(lib_early_sigma)-mc_early_sigma, 'CDNS_Lib_Early_Sigma_Rel': (np.array(lib_early_sigma)-mc_early_sigma)/mc_early_sigma, 'MC_Early_Sigma_LB': mc_early_sigma_lb, 'MC_Early_Sigma_UB': mc_early_sigma_ub,
                    'MC_Late_Sigma': mc_late_sigma, 'CDNS_Lib_Late_Sigma': lib_late_sigma, 'CDNS_Lib_Late_Sigma_Dif': np.array(lib_late_sigma)-mc_late_sigma, 'CDNS_Lib_Late_Sigma_Rel': (np.array(lib_late_sigma)-mc_late_sigma)/mc_late_sigma, 'MC_Late_Sigma_LB': mc_late_sigma_lb, 'MC_Late_Sigma_UB': mc_late_sigma_ub,
                    'MC_Std': mc_std, 'CDNS_Lib_Std': lib_std_dev, 'CDNS_Lib_Std_Dif': np.array(lib_std_dev)-mc_std, 'CDNS_Lib_Std_Rel': (np.array(lib_std_dev)-mc_std)/mc_std, 'MC_Std_LB': mc_std_lb, 'MC_Std_UB': mc_std_ub,
                    'MC_Skew': mc_skew, 'CDNS_Lib_Skew': lib_skewness, 'CDNS_Lib_Skew_Dif': np.array(lib_skewness)-mc_skew, 'CDNS_Lib_Skew_Rel': (np.array(lib_skewness)-mc_skew)/mc_skew, 'MC_Skew_LB': mc_skew_lb, 'MC_Skew_UB': mc_skew_ub,
                    'MC_Meanshift': mc_mean_shift, 'CDNS_Lib_Meanshift': lib_mean_shift, 'CDNS_Lib_Meanshift_Dif': np.array(lib_mean_shift)-mc_mean_shift, 'CDNS_Lib_Meanshift_Rel': (np.array(lib_mean_shift)-mc_mean_shift)/mc_mean_shift, 'MC_Meanshift_LB': mc_mean_shift_lb, 'MC_Meanshift_UB': mc_mean_shift_ub,
                    'Table_Type': fmc_txt_df['Table_Type']}
 
if args.mode == 'Hold':
    mc_late_sigma = fmc_txt_df['MC_Late_Sigma'].astype(float)
    mc_late_sigma_lb = fmc_txt_df['MC_Late_Sigma_LB'].astype(float)
    mc_late_sigma_ub = fmc_txt_df['MC_Late_Sigma_UB'].astype(float)
 
    if len(mc_late_sigma) != len(lib_late_sigma):
        false_index = [index for index, value in enumerate(arc_found) if value is False]
        arc_list = fmc_txt_df.iloc[false_index]['Arc']
        print(f"Warning: These Arcs {arc_list} not found")
 
    if args.nominal_check:
        mc_nominal = fmc_txt_df['MC_Nominal'].astype(float)
        csv_info = {'Cell_Name': fmc_txt_df['Cell_Name'], 'Arc': fmc_txt_df['Arc'],
                    'MC_Nominal': mc_nominal, 'CDNS_Lib_Nominal': lib_nominal, 'CDNS_Lib_Nominal_Dif': np.array(lib_nominal)-mc_nominal, 'CDNS_Lib_Nominal_Rel': (np.array(lib_nominal)-mc_nominal)/mc_nominal,
                    'MC_Late_Sigma': mc_late_sigma, 'CDNS_Lib_Late_Sigma': lib_late_sigma, 'CDNS_Lib_Late_Sigma_Dif': np.array(lib_late_sigma)-mc_late_sigma, 'CDNS_Lib_Late_Sigma_Rel': (np.array(lib_late_sigma)-mc_late_sigma)/mc_late_sigma, 'MC_Late_Sigma_LB': mc_late_sigma_lb, 'MC_Late_Sigma_UB': mc_late_sigma_ub,
                    'Table_Type': fmc_txt_df['Table_Type']}
    else:
        csv_info = {'Cell_Name': fmc_txt_df['Cell_Name'], 'Arc': fmc_txt_df['Arc'],
                    'MC_Late_Sigma': mc_late_sigma, 'CDNS_Lib_Late_Sigma': lib_late_sigma, 'CDNS_Lib_Late_Sigma_Dif': np.array(lib_late_sigma)-mc_late_sigma, 'CDNS_Lib_Late_Sigma_Rel': (np.array(lib_late_sigma)-mc_late_sigma)/mc_late_sigma, 'MC_Late_Sigma_LB': mc_late_sigma_lb, 'MC_Late_Sigma_UB': mc_late_sigma_ub,
                    'Table_Type': fmc_txt_df['Table_Type']}
 
# Create final dataframe and save
csv_info_df = pd.DataFrame(csv_info)
print(csv_info_df)
 
csv_info_df.to_csv('{}_fmc_cdns_lib_comp.rpt'.format(basename_noext), mode='w', index=False)

# Report FMC golden arcs not covered by the lib (req: use whatever is available,
# but report the mismatch entries). Uncovered arcs have NaN lib values and are
# excluded from the pass-rate denominator downstream.
total_golden = len(fmc_txt) - 1
if missing_arcs:
    miss_file = '{}_missing_arcs.txt'.format(basename_noext)
    with open(miss_file, 'w') as mf:
        mf.write('\n'.join(missing_arcs) + '\n')
    print(f"WARNING: {len(missing_arcs)}/{total_golden} golden arcs NOT covered by lib; listed in {miss_file}")
else:
    print(f"All {total_golden} golden arcs covered by lib.")

# Per-arc lib-lookup diagnostics: pinpoint WHY a lib value is 0/NaN
# (cell/pin found? how many timing groups? how many matched? extracted values?).
import csv as _csv_dbg
_dbg_file = '{}_lookup_debug.csv'.format(basename_noext)
with open(_dbg_file, 'w', newline='') as _df:
    _w = _csv_dbg.DictWriter(_df, fieldnames=[
        'Arc', 'cell_found', 'pin_found', 'n_timing', 'n_matched',
        'lib_early', 'lib_late', 'when', 'fir_index', 'sec_index'])
    _w.writeheader()
    _w.writerows(lookup_debug)
_zero = sum(1 for d in lookup_debug if (d['lib_early'] == 0 or d['lib_late'] == 0))
_nomatch = sum(1 for d in lookup_debug if d['n_matched'] == 0)
print(f"Lookup diagnostics: {_dbg_file} | arcs with a zero lib value={_zero} | arcs with no matched timing group={_nomatch}")
