# FMC Combine_data fixtures

PR 2 byte-identical regression fixtures must be produced from realistic FMC
outputs and legacy `2-data_process/Combine_data/calculate.py`. Do not hand-write
expected CSVs.

Expected fixture layout:

```text
tests/fixtures/fmc_combine_data/
├── input/
│   └── gen_DECKs/
│       └── ssgnp_0p450v_m40c_DECKS/
│           ├── delay/DECKS/{delay_arc_dir}/fastmontecarlo.log
│           ├── slew/DECKS/{slew_arc_dir}/fastmontecarlo.log
│           ├── hold/DECKS/{hold_arc_dir}/summary*.csv
│           └── mpw/DECKS/{mpw_arc_dir}/summary*.csv
└── expected/
    ├── fmc_result_n2p_v1p0_ssgnp_0p450v_m40c_delay.csv
    ├── fmc_result_n2p_v1p0_ssgnp_0p450v_m40c_slew.csv
    ├── fmc_result_n2p_v1p0_ssgnp_0p450v_m40c_hold.csv
    └── fmc_result_n2p_v1p0_ssgnp_0p450v_m40c_mpw.csv
```

Generate each expected CSV from the legacy script in a sandbox directory because
legacy `calculate.py` writes outputs to the current working directory:

```bash
# Generate expected CSV from legacy script
cd /tmp/legacy_fixture_gen  # any sandbox directory
python /path/to/2-data_process/Combine_data/calculate.py \
    /path/to/tests/fixtures/fmc_combine_data/input/gen_DECKs/ssgnp_0p450v_m40c_DECKS/delay/DECKS \
    n2p_v1p0 \
    ssgnp_0p450v_m40c \
    delay
# legacy writes fmc_result_n2p_v1p0_ssgnp_0p450v_m40c_delay.csv to cwd
mv fmc_result_n2p_v1p0_ssgnp_0p450v_m40c_delay.csv \
   /path/to/tests/fixtures/fmc_combine_data/expected/
# repeat for slew / hold / mpw
```

For hold/mpw, include at least two `summary*.csv` files per arc so regression
coverage verifies that the largest numeric summary file is selected.
