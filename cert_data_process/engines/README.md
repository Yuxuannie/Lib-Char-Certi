# engines/ — relocated legacy compute engines

Runtime-canonical copies of the legacy scripts the pipeline shells out to:

| Stage wrapper | Engine |
|---|---|
| `stages/lib_join_sigma.py` | `combine/Combine_FMC_and_CDNS_lib.py` (+ `run_ldbx.tcl`) |
| `stages/get_pr_sigma.py` | `get_pr/Sigma/check_sigma_with_waivers.py` |
| `stages/get_pr_moments.py` | `get_pr/Moments/check_moments_from_fmc.py` (imports `../Sigma`) |

Originals live in `archive/2-data_process/` (repo reference tree, excluded from delivery).
`Combine` requires the EDA-provided `ldbx` module; all engines require pandas/numpy.
