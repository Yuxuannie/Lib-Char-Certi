#!/bin/csh -f
source /tools/dotfile_new/cshrc.liberate 23.1.3.028.isr3
 
setenv ALTOS_MEMORY_OPTIMIZATION_OFF 1
 
set base_dir = "/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2024/N2P"
set rpt_dir = "${base_dir}/1-FMC_Golden/data_process/Combine_data"
set script_dir = "${base_dir}/7-final_results/0-scripts/Sigma/combine_mc_and_lib/"
set volts = (0p450v 0p465v 0p480v 0p495v)
#set volts = (0p450v)
 
## Recipe_1
set lib_dir = "${base_dir}/7-final_results/2-SNPS/libs/R1/"
set run_dir = "${base_dir}/7-final_results/2-SNPS/R1/sigma/"
 
## Recipe_4
# set lib_dir = "${base_dir}/7-final_results/2-SNPS/libs/R4/"
# set run_dir = "${base_dir}/7-final_results/2-SNPS/R4/sigma/"
 
 
foreach volt ($volts)
    cd $rpt_dir
    foreach rpt_file (fmc*${volt}*.csv)
                  set run_rpt_file = $rpt_file
        echo $run_rpt_file
 
 
        if ($run_rpt_file =~ *_hold.csv) then
          # for hold is cons.lib; for delay and slew is non_cons.lib
            cd $lib_dir
            foreach lib_file (*${volt}*T.cons.lib)
                set run_lib_file = $lib_file
                echo $run_lib_file
 
                cd $run_dir
                liberate --trio ${script_dir}/run_ldbx.tcl ${script_dir}/Combine_FMC_and_SNPS_lib.py \
                   -lib_path  $lib_dir/$run_lib_file\
                   -txt_path  $rpt_dir/$run_rpt_file\
                   -mode 'Hold' -nominal_check
            end
        endif
 
        cd $rpt_dir
        if ($run_rpt_file =~ *_delay.csv) then
            cd $lib_dir
            foreach lib_file (*${volt}*non_cons.lib)
                          set run_lib_file = $lib_file
                          echo $run_lib_file
 
                cd $run_dir
                liberate --trio ${script_dir}/run_ldbx.tcl ${script_dir}/Combine_FMC_and_SNPS_lib.py \
                   -lib_path  $lib_dir/$run_lib_file\
                   -txt_path  $rpt_dir/$run_rpt_file\
                   -mode 'Delay' -nominal_check
            end
        endif
 
        cd $rpt_dir
        if ($run_rpt_file =~ *_slew.csv) then
            cd $lib_dir
            foreach lib_file (*${volt}*non_cons.lib)
                          set run_lib_file = $lib_file
                          echo $run_lib_file
 
                cd $run_dir
                liberate --trio ${script_dir}/run_ldbx.tcl ${script_dir}/Combine_FMC_and_SNPS_lib.py \
                   -lib_path  $lib_dir/$run_lib_file\
                   -txt_path  $rpt_dir/$run_rpt_file\
                   -mode 'Slew' -nominal_check
            end
        endif
    end
end
 
 
