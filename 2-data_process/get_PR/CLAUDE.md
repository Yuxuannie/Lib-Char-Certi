# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a library characterization certification toolkit for semiconductor design, specifically focused on analyzing statistical moments and sigma values from Monte Carlo simulations. The codebase validates library characterization data against statistical criteria for timing analysis certification.

## Architecture

### High-Level Structure

```
get_PR/
├── Moments/           # Moments pass rate analysis
│   ├── check_moments.py    # Main moments validation script
│   ├── check_moments.sh    # Shell wrapper for moments analysis
│   └── run_ldbx.tcl       # Tcl helper script
└── Sigma/             # Sigma pass rate analysis
    ├── check_sigma.py      # Main sigma validation script
    └── check_sigma.sh      # Shell wrapper for sigma analysis
```

### Core Components

**Moments Analysis** (`Moments/`):
- Validates statistical moments (standard deviation, skew, mean shift) from Monte Carlo data
- Uses dual criteria: relative error thresholds OR absolute error thresholds
- Generates enhanced visualizations with parameter separation and grouping
- Integrates with sigma analysis results for combined reporting

**Sigma Analysis** (`Sigma/`):
- Implements four-tier checking system for sigma validation
- Uses CI bounds enlargement methodology for waived results
- Auto-detects CDNS vs SNPS vendor data formats
- Supports delay, slew, and hold constraint analysis

### Data Flow

1. Input: RPT files with Monte Carlo simulation results and library characterization data
2. Processing: Statistical validation using configurable thresholds and criteria
3. Output: Pass rate tables, detailed reports, and visualization charts

## Development Commands

### Running Analysis Scripts

**Legacy Analysis (Original System):**
```bash
cd Moments/
./check_moments.sh  # Original moments analysis

cd Sigma/
./check_sigma.sh    # Original sigma analysis
```

**NEW: Unified Waiver System Analysis:**
```bash
cd Moments/
./check_moments_with_waivers.sh  # Moments with 4 pass rates

cd Sigma/
./check_sigma_with_waivers.sh    # Sigma with 4 pass rates
```

**Direct Python Execution:**
```bash
# Legacy systems
python3 Moments/check_moments.py
python3 Sigma/check_sigma.py --root_path /path/to/data --corners corner1 corner2 --types delay slew --log_level INFO

# NEW: Waiver systems
python3 Moments/check_moments_with_waivers.py
python3 Sigma/check_sigma_with_waivers.py --root_path /path/to/data --corners corner1 corner2 --types delay slew hold --log_level INFO
```

### Expected Input Files

**Moments:** Files matching pattern `MC*{corner}*{type}*.rpt`
**Sigma:** Files matching pattern `fmc*{corner}*{type}*.rpt`

### Dependencies

- Python 3.9+
- pandas
- numpy
- matplotlib (for visualizations)

## Key Configuration Points

### Validation Thresholds

**Moments Analysis:**
- Delay: meanshift ≤1%, std ≤2%, skew ≤5%, abs ≤max(0.005×slew, 1ps)
- Slew: meanshift ≤2%, std ≤4%, skew ≤10%, abs ≤max(0.005×slew, 2ps)

**Sigma Analysis (Four-Tier System):**
- Tier 1: Relative error ≤ threshold (delay: 3%, slew: 6%, hold: 3%)
- Tier 2: Value within original CI bounds
- Tier 3: Value within CI + 6% enlargement (waived)
- Tier 4: Absolute error ≤ slew-dependent threshold

### Output Files

**Legacy Outputs:**
- CSV tables for integration (`sigma_PR_table_moments.csv`)
- Detailed analysis reports with 1-digit precision
- Visualization charts (PNG) with tier analysis
- Individual corner/type result files

**NEW: Waiver System Outputs:**
- `sigma_PR_table_with_waivers.csv` / `moments_PR_table_with_waivers.csv`: Tables with 4 pass rate columns
- `optimistic_pessimistic_breakdown.txt`: Detailed error direction analysis
- Enhanced visualizations with 4-bar comparison showing Base PR, PR+Waiver1, PR Optimistic Only, PR+Both Waivers
- Individual waiver result files with detailed columns per requirement

### Environment Variables

Key variables used by shell scripts:
- `combined_data_root_path`: Root directory containing input files
- `corners`: Space-separated list of corner names
- `types`: Space-separated list of analysis types
- `timestamp`: Used for logging and file naming

## Integration Notes

**Legacy Workflow:**
The moments analysis script reads sigma results from `sigma_PR_table.csv` to generate combined summary reports. Run sigma analysis first, then moments analysis for complete certification validation.

**NEW: Unified Waiver System:**

### Waiver System Features
1. **Base Pass/Fail Criteria (No Waivers):**
   - Check 1: Error-Based Pass (`rel_pass OR abs_pass`)
   - Check 2: CI Bounds Pass (lib value within MC CI bounds)
   - Base Pass = `Check 1 OR Check 2`

2. **Waiver System:**
   - **Waiver 1:** CI Enlargement (CI ± 6%)
   - **Waiver 2:** Optimistic Error Only (lib < mc, "library claims better performance")

3. **4 Pass Rate Types Generated:**
   - `Base_PR`: Base criteria only
   - `PR_with_Waiver1`: Base + CI enlargement
   - `PR_Optimistic_Only`: Only optimistic errors considered
   - `PR_with_Both_Waivers`: Optimistic errors + CI enlargement

### Waiver Workflow
1. Run `check_sigma_with_waivers.sh` for sigma waiver analysis
2. Run `check_moments_with_waivers.sh` for moments waiver analysis
3. Compare results using generated visualizations and breakdown analysis
4. Both systems maintain backward compatibility with original outputs

### Key Implementation Details
- **Error Direction:** Optimistic = `lib_value < mc_value` (library claims better performance than MC reality)
- **CI Enlargement:** 6% expansion of confidence interval bounds for waived results
- **Output Structure:** Each CSV contains detailed columns: `Arc`, `Parameter`, `MC_value`, `Lib_value`, `MC_CI_LB`, `MC_CI_UB`, `abs_err`, `rel_err`, `Base_Pass`, `Pass_Reason`, `Waiver1_CI_Enlarged`, `Error_Direction`, `Final_Status`
- **Visualizations:** Enhanced 4-bar charts plus optimistic vs pessimistic error distribution charts