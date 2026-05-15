"""Configuration model for the cert_data_process CLI skeleton."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple

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

    @property
    def run_sigma(self) -> bool:
        """Whether the FMC/Sigma branch should run."""

        return self.fmc_golden_dir is not None

    @property
    def run_moments(self) -> bool:
        """Whether the Full-MC/Moments branch should run."""

        return self.full_mc_golden_dir is not None

    def to_manifest_dict(self) -> dict:
        """Return a JSON-serializable representation for run_manifest.json."""

        data = asdict(self)
        for key in ("lib_dir", "output_dir", "fmc_golden_dir", "full_mc_golden_dir"):
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

    if not fmc_golden_dir and not full_mc_golden_dir:
        raise ValueError("at least one of --fmc-golden-dir or --full-mc-golden-dir is required")

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
    )
