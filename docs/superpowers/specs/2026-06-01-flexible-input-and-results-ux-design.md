# Flexible FMC Input + Results UX + Logging + Restyle

Date: 2026-06-01
Status: approved (user approved A; asked to implement B/C/D together; E deferred).

## A. Flexible FMC golden input (priority)

Pipeline's first stage becomes mode-aware; all modes converge on the same
`normalized/fmc/fmc_result_<node>_<corner>_<type>.csv`, so lib-join → check_sigma
→ moments are unchanged.

| Mode | Input | Action |
|---|---|---|
| `decks` (current) | deck dirs | existing `fmc_combine_data` (unchanged) |
| `parsed_dfds` | DFDS tables (already in target format) | validate columns + place into normalized/fmc |
| `parsed_scld` | SCLD `delay`+`cons` files | adapter: filter by `type` → map → rebuild Arc → ns→ps → write normalized CSVs |

**SCLD specifics** (`parsers/fmc_scld_adapter.py`, pure functions):
- `delay` file rows: `type=delay`→delay.csv, `type=slew`→slew.csv (early+late sigma, meanshift, std, skew).
- `cons` file rows: `type=hold`→hold.csv, `type=min_pulse_width`→mpw.csv (late-sigma only).
- Column map: Cell→Cell_Name, pin→output_pin, pin_dir→output_pin_dir, rel_pin/rel_pin_dir→same,
  when→when, index_1/2→first/sec_index.
- Units: nominal / ocv_*_sigma / ocv_mean_shift / ocv_std_dev → MC_* ×1000 (ns→ps).
  **ocv_skewness → MC_Skew unscaled** (dimensionless).
- Table_Type from type+pin_dir: delay→cell_rise/cell_fall, slew→rise/fall_transition,
  hold/mpw→rise/fall_constraint.
- Arc rebuilt: `<prefix>_<cell>_<outpin>_<outdir>_<relpin>_<reldir>_<when-tokens>_<idx1>_<idx2>`,
  `!X→notX`, none→`NO_CONDITION`. prefix: combinational (delay/slew), hold (hold),
  min_pulse_width (mpw) — only the mpw prefix is semantically parsed downstream.
- Corner token derived from the SCLD filename; must match `--corners` + lib filenames
  (same corner-match rule). User confirms alignment on first real run.

**CLI/config**: add `fmc_mode ∈ {decks, parsed_dfds, parsed_scld}` + `fmc_input_dir`.
Keep `--fmc-golden-dir` = decks (back-compat). **GUI Setup**: "FMC input" dropdown.

## B. Results UX (per-type, verdict, color, export)

- Results regrouped by **type** (delay / slew / hold / mpw), NOT sigma/moments. Each
  type section is one table: rows = corners, columns = the metrics for that type:
  - delay, slew: Early_Sigma, Late_Sigma, Meanshift, Std, Skew (sigma + moments merged by corner+type).
  - hold, mpw: Late_Sigma only.
- 95% is the criterion. **Certification verdict** = PASS iff every shown type-metric
  pass rate (across all corners) ≥ 95%; else FAIL, with a prominent banner.
- Color each pass-rate cell: green ≥95, amber 90–<95, red <90.
- **Export to CSV**: one flat, copiable table of all (corner,type,metric) pass rates →
  written to a file in the run dir (+ a copy-to-clipboard convenience).

## C. Pipeline log + error surfacing

- A live high-level log area (per run) showing stage transitions and outcomes.
- On a stage failure, surface a clear message and write a single consolidated
  failures file (e.g. `<run>/failures_summary.txt`) listing the failing items
  (e.g. decks missing `summary*.csv`), and point the user to it in the log + Results.

## D. UI restyle

Another styling pass for a cleaner, more professional look (within Tk's limits):
spacing, fonts, section headers, the green/amber/red treatment from B, verdict banner.

## E. Deferred (next discussion)
Results analysis, outlier analysis, waiver_2 (abs_tol per library), waiver_3
(voltage margin). Not in this spec.

## Testing
- A: unit-test the SCLD adapter (filter/map/Arc/units/Table_Type/split) + DFDS
  validation with tiny synthetic CSVs (no liberate/display).
- B: unit-test the per-type merge + cert-verdict + CSV-export helpers (pure functions).
- GUI itself needs a display; rely on import-safety + the pure-helper tests.
