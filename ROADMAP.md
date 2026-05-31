# Lib-Char-Certi Roadmap

Set 2026-05-31. North star for the in-progress rework. Order reflects dependency.

## G1 — Drop optimistic PR columns ✅ (in progress)
Remove `PR_Optimistic_Only` and `PR_with_Both_Waivers` from sigma/moments PR
output. Keep only `Base_PR` and `PR_with_Waiver1` (CI +6%). A dedicated
optimistic-analysis module will live in the future GUI analysis section, not in
the core PR table.

## G2 — Honest, data-aware logging  (in progress)
Logs and PR output must make the **data situation** unmistakable. Concretely:
- Every PR figure is shown with its denominator: covered / total arcs.
- A `Data_Health` flag per (corner,type): OK / LOW_COVERAGE / NO_DATA.
- Loud warning when lib covers few/zero required cells, so a misleading "100%
  PR over 0 real cells" (the N2P v1.0 case) is impossible.
- Surface cell-match + arc-coverage from combine/lib_join through to the PR table.

## G3 — Refactor: decouple from legacy scripts
Package (`cert_data_process`) currently shells out to `2-data_process/*` legacy
scripts. Target: native, importable stage modules; legacy scripts become
reference only. Incremental (keep the flow working each step), not big-bang.

## G4 — Moments from FMC only (major change)
Drop the Full-MC dependency. Compute moments (meanshift / std / skew) Base_PR
and Base_PR+Waiver1 directly from the FMC combined data in a single pass
(MC_Std/Skew/Meansht + lib std/skew/mean already exist in the combine RPT).

## G5 — User-friendly GUI
Front-end over the pipeline + outputs. Will host an analysis section (incl. the
optimistic analysis deferred from G1).

## G6 — History + multi-batch
Persistent run history. Support multiple batches per run: one batch = one EDA
recipe = the current "multiple corner" scope. Need to compare several recipes.

## Known open bug
v0.9 hold decks: `summary.N.csv` (e.g. `summary.1.csv`, latest = largest N) in
some arc dirs reported `missing_summary_csv` (60 failures). Need ls of an arc
dir to see real layout (likely nested in rerun subdirs). Fix `parse_summary_csv`
discovery (recursive + max trailing N) without touching delay/slew path.
