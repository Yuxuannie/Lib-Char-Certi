# Self-contained package + clean delivery — design

Date: 2026-06-18
Branch: `refactor/self-contained-package`

## Problem

`cert_data_process/` is the v1 deliverable but is **not self-contained**: at run
time it shells out to legacy scripts that live *outside* the package, under
`2-data_process/`:

| Stage wrapper | Legacy script invoked |
|---|---|
| `stages/lib_join_sigma.py` | `2-data_process/Combine_Lib_and_FMC/Combine_FMC_and_CDNS_lib.py` + `run_ldbx.tcl` |
| `stages/get_pr_sigma.py` | `2-data_process/get_PR/Sigma/check_sigma_with_waivers.py` |
| `stages/get_pr_moments.py` | `2-data_process/get_PR/Moments/check_moments_from_fmc.py` |

`stages/pr_web_app.py` and `web/server.py` also reach out to `gui/certi_console.html`
(top-level). So the package depends on the repo layout, the top-level folder
structure is cluttered, and a delivery ZIP cannot simply exclude legacy without
breaking real runs.

`1-Parse/` is reference-only (no runtime caller). The bulk of `2-data_process/`
(Combine_data, Plot, Validate_CI, *.rpt, backup/variant scripts) is reference-only.

## Goal

Make `cert_data_process/` self-contained so the delivery is a single package, and
produce a clean delivery ZIP that excludes reference-only legacy and dev-only files.
Keep the legacy reference trees in the repo (per project rule: legacy is the
reference standard, do not delete).

## Target structure

```
cert_data_process/
├── cli.py  config.py  audit.py  __init__.py
├── analysis/   parsers/                 (unchanged)
├── stages/                              (path resolution: 2-data_process/… → engines/…)
├── engines/                             NEW — relocated live legacy engines (runtime dep)
│   ├── __init__.py
│   ├── combine/
│   │   ├── Combine_FMC_and_CDNS_lib.py
│   │   ├── Combine_FMC_and_SNPS_lib.py
│   │   └── run_ldbx.tcl
│   └── get_pr/
│       ├── Sigma/check_sigma_with_waivers.py
│       └── Moments/check_moments_from_fmc.py    (imports ../Sigma sibling — preserved)
├── runtime/                             RENAMED from web/
│   ├── runs.py summary.py executor.py server.py __main__.py __init__.py
├── web_assets/certi_console.html        moved from top-level gui/
└── demo_run/                            (demo data)
```

## Decisions

1. **COPY engines, don't move.** `engines/` is the runtime canonical copy. The
   originals stay in `2-data_process/` as reference (excluded from delivery). The
   only duplication is in-repo, never in the delivery ZIP.
2. **`web/` → `runtime/`.** "web" is misleading for a desktop tool; the module is
   the run/session data layer plus the no-Tk HTTP fallback. Highest-churn cosmetic
   change (~6 import sites); tests cover it.
3. **HTML console moves into the package** (`web_assets/`), so `pr_web_app.py` and
   `runtime/server.py` no longer reach `parents[2]/gui/`.
4. **Engines stay subprocess-invoked** (unchanged execution model); only the
   resolved script path changes. `cwd` is preserved as the delivery root
   (`parents[2]`), since the scripts take all I/O paths via args.

## Delete (verified redundant only)

- `scripts/compare_fmc_csv_byte_equal.py`, `scripts/compare_mc_csv_byte_equal.py`
  (byte-equal acceptance dropped — CLAUDE.md §2.3)
- top-level `moments_check_*.log`, stray `.DS_Store`

## Delivery packaging

- `.gitattributes` with `export-ignore` on: `1-Parse/`, `2-data_process/`,
  `docs/superpowers/`, `ROADMAP.md`, `tests/`, `scripts/`, `CLAUDE.md`,
  `gui/` (now empty).
- `scripts/make_delivery.sh` → `git archive` → `Lib-Char-Certi-v1.0.0.zip`.
- `3-Voltage_Margin_Tool/` is untracked (gitignored) → not in archive anyway.

## Dependencies

- `pyproject.toml`: add **pandas, numpy** as required (real runs need them; the
  relocated engines import them). Currently nothing is declared.
- `ldbx` (Cadence Liberate Python module) is EDA-environment-provided — documented,
  not pip-declared.
- `matplotlib` stays an optional `[plots]` extra.

## Risks / verification

- Engine relocation changes the subprocess script path. `check_sigma` / `check_moments`
  are pure pandas and can be regression-checked locally with fixtures + the demo.
- **`Combine` (lib_join) imports `ldbx`, which cannot be installed locally** — the
  combine path can only be fully verified in the EDA environment. The plan runs the
  full test suite + the demo render; the combine path is path-verified (correct
  resolved location + existence) but the user confirms a real run on the host.
- Latent, out-of-scope bug noted: `lib_join_sigma.py` hardcodes the CDNS combine
  script regardless of vendor. Not fixed here; both variants relocated so a future
  fix has them.
- Fix the misleading `build_pr_table` note in `cli.py:PLANNED_STAGE_STATUS`
  ("Native" → engine-backed via `engines/get_pr/Sigma`).

## Out of scope

VM/Voltage-Margin (hidden in v1), the SNPS-combine vendor-selection bug, any
change to PR logic or numbers.
