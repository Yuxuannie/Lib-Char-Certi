"""Configuration model for the cert_data_process CLI skeleton."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Tuple

SUPPORTED_VENDORS = ("cdns", "snps")
SUPPORTED_TYPES = ("delay", "slew", "hold", "mpw")


@dataclass(frozen=True)
class CertDataProcessConfig:
    """Validated CLI configuration for a data_process run.

    Phase 1 PR 1 only materializes the output tree and manifest. Later PRs will
    pass this same config object to each functional stage.
    """

    vendor: str
    process: str
    process_version: str
    corners: Tuple[str, ...]
    types: Tuple[str, ...]
    lib_dir: Path
    output_dir: Path
    fmc_golden_dir: Optional[Path] = None
    full_mc_golden_dir: Optional[Path] = None
    full_mc_keep_raw_samples: bool = False
    # FMC input mode: "decks" (parse decks via fmc_combine_data),
    # "parsed_dfds" (already-parsed DFDS tables), "parsed_scld" (SCLD files).
    fmc_mode: str = "decks"
    fmc_input_dir: Optional[Path] = None
    # Optional metadata + parsed-file disambiguation (free-form):
    # VT type e.g. svt/elvt; RC type e.g. cworst/cbest/typical.
    vt_type: str = ""
    rc_type: str = ""
    # Library structure hint: "base" | "mb" (multi-bit) | "auto". Metadata only;
    # lib-join pin lookup is always bundle-aware, so this does not gate correctness.
    library_type: str = "auto"
    # Waiver_2 (abs_tol): user-assigned absolute tolerance in ps, per corner. Applies
    # to HOLD Late_Sigma only. A hold arc with |Lib-MC| <= abs_tol[corner] is waived.
    # User-provided only — never inferred. Empty/missing corner => waiver_2 inactive there.
    abs_tol_ps_by_corner: Dict[str, float] = field(default_factory=dict)

    @property
    def run_sigma(self) -> bool:
        """Whether the FMC/Sigma branch should run (decks or already-parsed input)."""

        return self.fmc_golden_dir is not None or self.fmc_input_dir is not None

    @property
    def run_moments(self) -> bool:
        """Whether the Full-MC/Moments branch should run."""

        return self.full_mc_golden_dir is not None

    def to_manifest_dict(self) -> dict:
        """Return a JSON-serializable representation for run_manifest.json."""

        data = asdict(self)
        for key in ("lib_dir", "output_dir", "fmc_golden_dir", "full_mc_golden_dir", "fmc_input_dir"):
            value = data[key]
            data[key] = str(value) if value is not None else None
        data["run_sigma"] = self.run_sigma
        data["run_moments"] = self.run_moments
        return data


def parse_csv(value: str, *, field_name: str) -> Tuple[str, ...]:
    """Parse a comma-separated CLI value and reject empty entries."""

    items = tuple(item.strip() for item in value.split(",") if item.strip())
    if not items:
        raise ValueError(f"--{field_name} must contain at least one value")
    return items


def validate_types(types: Sequence[str]) -> Tuple[str, ...]:
    """Validate requested timing types."""

    unsupported = sorted(set(types) - set(SUPPORTED_TYPES))
    if unsupported:
        raise ValueError(
            "unsupported --types value(s): "
            + ", ".join(unsupported)
            + f"; supported values are: {', '.join(SUPPORTED_TYPES)}"
        )
    return tuple(types)


def build_config(
    *,
    vendor: str,
    process: str,
    process_version: str,
    corners: Iterable[str],
    types: Iterable[str],
    lib_dir: str,
    output_dir: str,
    fmc_golden_dir: Optional[str] = None,
    full_mc_golden_dir: Optional[str] = None,
    full_mc_keep_raw_samples: bool = False,
    fmc_mode: str = "decks",
    fmc_input_dir: Optional[str] = None,
    vt_type: str = "",
    rc_type: str = "",
    library_type: str = "auto",
    abs_tol_ps_by_corner: Optional[Dict[str, float]] = None,
) -> CertDataProcessConfig:
    """Build and validate a :class:`CertDataProcessConfig`."""

    normalized_vendor = vendor.lower()
    if normalized_vendor not in SUPPORTED_VENDORS:
        raise ValueError(
            f"unsupported --vendor value: {vendor}; supported values are: "
            + ", ".join(SUPPORTED_VENDORS)
        )

    corner_tuple = tuple(corner.strip() for corner in corners if corner.strip())
    if not corner_tuple:
        raise ValueError("--corners must contain at least one value")

    type_tuple = validate_types(tuple(type_name.strip() for type_name in types if type_name.strip()))
    if not type_tuple:
        raise ValueError("--types must contain at least one value")

    supported_modes = ("decks", "parsed_dfds", "parsed_scld")
    if fmc_mode not in supported_modes:
        raise ValueError(f"unsupported --fmc-mode value: {fmc_mode}; supported: {', '.join(supported_modes)}")

    if fmc_mode == "decks":
        if not fmc_golden_dir and not full_mc_golden_dir:
            raise ValueError("at least one of --fmc-golden-dir or --full-mc-golden-dir is required")
    else:  # parsed_dfds / parsed_scld
        if not fmc_input_dir:
            raise ValueError(f"--fmc-input-dir is required for --fmc-mode {fmc_mode}")

    return CertDataProcessConfig(
        vendor=normalized_vendor,
        process=process,
        process_version=process_version,
        corners=corner_tuple,
        types=type_tuple,
        lib_dir=Path(lib_dir),
        output_dir=Path(output_dir),
        fmc_golden_dir=Path(fmc_golden_dir) if fmc_golden_dir else None,
        full_mc_golden_dir=Path(full_mc_golden_dir) if full_mc_golden_dir else None,
        full_mc_keep_raw_samples=full_mc_keep_raw_samples,
        fmc_mode=fmc_mode,
        fmc_input_dir=Path(fmc_input_dir) if fmc_input_dir else None,
        vt_type=(vt_type or "").strip(),
        rc_type=(rc_type or "").strip(),
        library_type=((library_type or "auto").strip().lower() or "auto"),
        abs_tol_ps_by_corner=_clean_abs_tol(abs_tol_ps_by_corner),
    )


def _clean_abs_tol(raw: Optional[Dict[str, float]]) -> Dict[str, float]:
    """Normalize the user-provided abs_tol map: trim corner keys, keep numeric > 0."""
    out: Dict[str, float] = {}
    for corner, val in (raw or {}).items():
        c = str(corner).strip()
        if not c:
            continue
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        if v > 0:
            out[c] = v
    return out
