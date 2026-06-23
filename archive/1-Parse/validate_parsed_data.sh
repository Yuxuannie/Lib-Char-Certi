#!/bin/bash
 
# Configuration
script_path="/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2025/N2P_v1.0/1-MC_golden/1-Full_MC_golden/0-script/1-Parse/"
output_folder="/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2025/N2P_v1.0/1-MC_golden/1-Full_MC_golden/Parse"
#output_folder="/SIM/DFDS_20211231/Personal/ynie/3-LibCharCerti/2025/N2P_v1.0/1-MC_golden/2-delivery/1st_round_golden/2-Full_MC/"
log_file="${script_path}/parse_mc_data.log"
validation_report="${script_path}/validation_report.txt"
 
# Timestamp function
timestamp() {
  date +"%Y-%m-%d %H:%M:%S"
}
 
# Divider function for report file
print_divider() {
  echo "=================================================================" >> "$validation_report"
}
 
print_section_header() {
  print_divider
  echo "                     $1                                          " >> "$validation_report"
  print_divider
}
 
# Initialize validation report
echo "DATA VALIDATION REPORT - Generated on: $(timestamp)" > "$validation_report"
print_divider
echo "Checking parsed data in: $output_folder" >> "$validation_report"
print_divider
 
# 1. Check the overall directory structure
print_section_header "DIRECTORY STRUCTURE"
 
# Count the number of corners processed
corner_count=$(ls -l "$output_folder/" | grep "^d" | wc -l)
echo "Total corners processed: $corner_count" >> "$validation_report"
echo "" >> "$validation_report"
 
# Count arcs processed for each corner
echo "Arc count per corner:" >> "$validation_report"
for corner in "$output_folder"/*; do
  if [ -d "$corner" ]; then
    arc_count=$(ls -l "$corner" | grep "^d" | wc -l)
    echo "$(basename "$corner"): $arc_count arcs" >> "$validation_report"
  fi
done
 
# 2. Verify file existence in each arc directory
print_section_header "FILE EXISTENCE CHECK"
 
# Check that each arc directory has both required files
echo "Checking for missing files in arc directories..." >> "$validation_report"
missing_files=0
 
find "$output_folder" -type d | while read -r dir; do
  if [ "$dir" != "$output_folder" ] && [ "$(dirname "$dir")" != "$output_folder" ]; then
    if [ ! -f "$dir/stats.csv" ] || [ ! -f "$dir/netlist_params.txt" ]; then
      echo "Missing files in: $dir" >> "$validation_report"
      missing_files=$((missing_files+1))
    fi
  fi
done
 
if [ $missing_files -eq 0 ]; then
  echo "All arc directories contain the required files." >> "$validation_report"
else
  echo "Found $missing_files directories with missing files." >> "$validation_report"
fi
 
# 3. Check for empty or small files
print_section_header "FILE SIZE CHECK"
 
# Find suspiciously small files (possible parsing errors)
echo "CSV files smaller than 100 bytes (potential parsing errors):" >> "$validation_report"
find "$output_folder" -name "stats.csv" -size -100c -exec ls -lh {} \; >> "$validation_report" 2>/dev/null
echo "" >> "$validation_report"
 
echo "TXT files smaller than 100 bytes (potential parsing errors):" >> "$validation_report"
find "$output_folder" -name "netlist_params.txt" -size -100c -exec ls -lh {} \; >> "$validation_report" 2>/dev/null
echo "" >> "$validation_report"
 
# 4. Check file size distribution
echo "CSV file size distribution:" >> "$validation_report"
find "$output_folder" -name "stats.csv" -exec ls -l {} \; | awk '{print $5}' | sort -n | uniq -c | sort -n >> "$validation_report"
echo "" >> "$validation_report"
 
echo "TXT file size distribution:" >> "$validation_report"
find "$output_folder" -name "netlist_params.txt" -exec ls -l {} \; | awk '{print $5}' | sort -n | uniq -c | sort -n >> "$validation_report"
 
# 5. Validate CSV format (sample)
print_section_header "CSV FORMAT VALIDATION (SAMPLE)"
 
# Sample some CSV files and check column count consistency
echo "Sampling CSV files to check column counts:" >> "$validation_report"
sample_count=0
for file in $(find "$output_folder" -name "stats.csv" | head -20); do
  echo -n "$(basename "$(dirname "$file")"): " >> "$validation_report"
  column_counts=$(awk -F, '{print NF}' "$file" | sort | uniq -c)
  echo "$column_counts" >> "$validation_report"
  sample_count=$((sample_count+1))
done
echo "Sampled $sample_count CSV files." >> "$validation_report"
 
# 6. Inspect the content of generated files (sample)
print_section_header "FILE CONTENT SAMPLES"
 
# Sample CSV headers
echo "Sample CSV headers:" >> "$validation_report"
find "$output_folder" -name "stats.csv" | head -5 | xargs head -1 >> "$validation_report" 2>/dev/null
echo "" >> "$validation_report"
 
# Sample TXT file content
echo "Sample TXT file content:" >> "$validation_report"
find "$output_folder" -name "netlist_params.txt" | head -3 | xargs head -5 >> "$validation_report" 2>/dev/null
 
# 7. Check for errors in log file
print_section_header "LOG FILE ANALYSIS"
 
echo "Errors and warnings from log file:" >> "$validation_report"
grep -i "error\|warning\|fail" "$log_file" | tail -20 >> "$validation_report" 2>/dev/null
echo "" >> "$validation_report"
 
echo "Success count from log file:" >> "$validation_report"
grep -i "success" "$log_file" | wc -l >> "$validation_report"
 
# 8. Generate summary statistics
print_section_header "SUMMARY STATISTICS"
 
total_arcs=0
total_csv=0
total_txt=0
 
for corner in "$output_folder"/*; do
  if [ -d "$corner" ]; then
    arc_count=$(find "$corner" -maxdepth 1 -type d | wc -l)
    arc_count=$((arc_count-1))  # Subtract 1 to account for the corner directory itself
    total_arcs=$((total_arcs + arc_count))
   
    csv_count=$(find "$corner" -name "stats.csv" | wc -l)
    txt_count=$(find "$corner" -name "netlist_params.txt" | wc -l)
    total_csv=$((total_csv + csv_count))
    total_txt=$((total_txt + txt_count))
  fi
done
 
echo "Total arcs processed: $total_arcs" >> "$validation_report"
echo "Total CSV files: $total_csv" >> "$validation_report"
echo "Total TXT files: $total_txt" >> "$validation_report"
echo "" >> "$validation_report"
 
echo "File size statistics:" >> "$validation_report"
echo "  - Smallest CSV: $(find "$output_folder" -name "stats.csv" -exec ls -l {} \; | sort -nk5 | head -1 | awk '{print $5 " bytes in " $9}')" >> "$validation_report"
echo "  - Largest CSV: $(find "$output_folder" -name "stats.csv" -exec ls -l {} \; | sort -nrk5 | head -1 | awk '{print $5 " bytes in " $9}')" >> "$validation_report"
echo "  - Smallest TXT: $(find "$output_folder" -name "netlist_params.txt" -exec ls -l {} \; | sort -nk5 | head -1 | awk '{print $5 " bytes in " $9}')" >> "$validation_report"
echo "  - Largest TXT: $(find "$output_folder" -name "netlist_params.txt" -exec ls -l {} \; | sort -nrk5 | head -1 | awk '{print $5 " bytes in " $9}')" >> "$validation_report"
 
print_section_header "VALIDATION COMPLETE"
 
echo "Validation report has been generated: $validation_report"
echo "Run 'cat $validation_report' to view the report."
 
# Optionally display the report
cat "$validation_report"
 
