import sys,os,pickle,math,re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
 
########################################################
input_file = sys.argv[1]
output_file = "Output/output.csv"
sep = '\s+'
criteria = [-0.03, 0.03]
item_list = ['delay_late', 'delay_early', 'meanshift', 'std', 'skewness']
########################################################
 
df = pd.read_csv(input_file, sep=sep)
df = df.rename( columns={'diff': 'diff_org', 'mc_err': 'mc_err_org' } )
 
def match_data(cellName):
    c = re.match(r"(.*D\d+P?\d?)", cellName)
    reduced_name = c.group(1)
    reduced_name = reduced_name.replace('MZ', '')
    return reduced_name
 
def calculate_error(row, lib_key, mc_key):
    lib_value = row[lib_key]
    mc_value = row[mc_key]
    if lib_key == 'lib_early_sigma':
        denominator = max( row['mid_point_early'], abs(row['nominal']) )
    elif lib_key == 'lib_late_sigma':
        denominator = max( row['mid_point_late'], abs(row['nominal']) )
    elif lib_key == 'lib_meanshift':
        denominator = row['nominal'] + row['mc_meanshift']
    elif lib_key == 'lib_std':
        denominator = row['nominal'] + row['mc_meanshift'] + row['mc_std']
    elif lib_key == 'lib_skewness':
        denominator = row['nominal'] + row['mc_meanshift'] + row['mc_skewness']
 
    mc_err_new = (lib_value - mc_value) / denominator
    return mc_err_new
 
 
def waive_CI(row, col, item):
    if row[col] == 'pass':
        return 'pass'
 
    if item == 'delay_early':
        upper_key = 'mc_early_sigma_ub'
        lower_key = 'mc_early_sigma_lb'
        lib_key = 'lib_early_sigma'
    elif item == 'delay_late':
        upper_key = 'mc_late_sigma_ub'
        lower_key = 'mc_late_sigma_lb'
        lib_key = 'lib_late_sigma'
    elif item == 'meanshift':
        upper_key = 'mc_meanshift_ub'
        lower_key = 'mc_meanshift_lb'
        lib_key = 'lib_' + item
    elif item == 'std':
        upper_key = 'mc_std_ub'
        lower_key = 'mc_std_lb'
        lib_key = 'lib_' + item
    elif item == 'skewness':
        upper_key = 'mc_skewness_ub'
        lower_key = 'mc_skewness_lb'
        lib_key = 'lib_' + item
    CIw = row[upper_key] - row[lower_key]
    lower_bound = row[lower_key] - (0.06 * CIw)
    upper_bound = row[upper_key] + (0.06 * CIw)
    lib_value = row[lib_key]
    if lib_value < lower_bound or lib_value > upper_bound:
        return 'fail'
    else:
        return 'pass_waive'
 
 
cellcount = len(df)
cell_set = set(df['cell'].to_list())
 
df['reduced_cell'] = df['cell'].apply(match_data)
df['mid_point_early'] = ( df['mc_early_sigma_lb'] + df['mc_early_sigma_ub'] ) / 2
df['mid_point_late'] = ( df['mc_late_sigma_lb'] + df['mc_late_sigma_ub'] ) / 2
 
axis_min_max = {}
for item in item_list:
    print("Processing ", item)
    target_error = 'mc_err_' + item
    if item == 'delay_early':
        lib_key = 'lib_early_sigma'
        mc_key = 'mid_point_early'
    elif item == 'delay_late':
        lib_key = 'lib_late_sigma'
        mc_key = 'mid_point_late'
    elif item == 'meanshift':
        lib_key = 'lib_meanshift'
        mc_key = 'mc_meanshift'
    elif item == 'std':
        lib_key = 'lib_std'
        mc_key = 'mc_std'
    elif item == 'skewness':
        lib_key = 'lib_skewness'
        mc_key = 'mc_skewness'
 
    df[target_error] = df.apply(calculate_error, args=(lib_key, mc_key) ,axis=1)
    pass_fail = 'PASS_FAIL_' + item
    df[pass_fail] = df[target_error].apply(lambda x: 'fail' if x < criteria[0] or x > criteria[1] else 'pass')
    df[pass_fail] = df.apply(waive_CI, args=(pass_fail, item), axis=1)
 
    vmin_ = df[target_error].min()
    vmax_ = df[target_error].max()
    axis_min_max[item] = (vmin_, vmax_)
   
df_violation = df[df['nominal'] - (3 * df['lib_early_sigma']) < 0 ]
df_violation.to_csv('early_violation.csv', index=False)
 
sort_cell_list = []
for item in item_list:
    print("Plot ", item, end=' ')
    vmin = axis_min_max[item][0]*100
    vmax = axis_min_max[item][1]*100
    print("min:", vmin, "   max:", vmax)
 
    PassingDict = {}
    target_error = 'mc_err_' + item
    pass_fail = 'PASS_FAIL_' + item
    for cell in cell_set:
        df_cell = df[df['cell'] == cell].copy()
        re_cell = match_data(cell)
        PassingDict[re_cell] = len(df_cell[df_cell[pass_fail] != 'fail']) / len(df_cell)
   
        df_cell[['X', 'Y']] = df_cell['point'].str.split('_', expand=True).astype(int)
        heatmap_data = np.zeros((8, 8))
       
        for index, row in df_cell.iterrows():
            x = row['X'] - 1
            y = row['Y'] - 1
            heatmap_data[x, y] = row[target_error] * 100
       
 
        labels = [str(i) for i in range(1, 9)]
        ax = sns.heatmap(heatmap_data, annot=True, fmt=".2f", cmap='coolwarm', xticklabels=labels, yticklabels=labels, vmin=vmin, vmax=vmax, center=0)
        plt.xlabel('X Index')
        plt.ylabel('Y Index')
        plt.title(cell)
    
        plt.savefig('HeatMap/' + cell + '_' + item + '.png')
        plt.close()
   
    
    print("***************************", item, "**************************************")
    if item == 'delay_late':
        sort_cell_list = sorted(PassingDict.items(), key=lambda item: item[1])
   
    for cell, pr in sort_cell_list:
        #print(cell, "Passing Rate: ", PassingDict[cell])
        print(cell, PassingDict[cell])
 
df.to_csv(output_file, index=False)
 
