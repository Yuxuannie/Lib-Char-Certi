"""FMC sigma lib-join stage (PR4 FMC-first path)."""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cert_data_process.config import CertDataProcessConfig


@dataclass(frozen=True)
class SigmaLibJoinResult:
    stage_execution: dict[str, Any]
    compatibility_stage_report: dict[str, Any]

    @property
    def failed(self) -> bool:
        return self.stage_execution["status"] == "failed"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_liberate_cmd(tcl: Path, script: Path, lib_file: Path, csv_path: Path, mode: str) -> list[str]:
    return [
        "liberate",
        "--trio",
        str(tcl),
        str(script),
        "-lib_path",
        str(lib_file),
        "-txt_path",
        str(csv_path),
        "-mode",
        mode,
        "-nominal_check",
    ]


def _build_liberate_shell_cmd(tcl: Path, script: Path, lib_file: Path, csv_path: Path, mode: str) -> str:
    base = " ".join(_build_liberate_cmd(tcl=tcl, script=script, lib_file=lib_file, csv_path=csv_path, mode=mode))
    return (
        "source /tools/dotfile_new/cshrc.liberate 23.1.3.028.isr3 && "
        "setenv ALTOS_MEMORY_OPTIMIZATION_OFF 1 && "
        f"{base}"
    )


def _corner_for_csv(csv_name: str, corners: tuple[str, ...]) -> str | None:
    """Return the requested corner whose name is embedded in this CSV filename.

    Prefer the longest match so a corner that is a substring of another does not
    shadow the more specific one.
    """

    matches = [c for c in corners if c in csv_name]
    if not matches:
        return None
    return max(matches, key=len)


def _mode_for_csv(csv_name: str) -> str:
    if csv_name.endswith("_hold.csv"):
        return "Hold"
    if csv_name.endswith("_delay.csv"):
        return "Delay"
    if csv_name.endswith("_slew.csv"):
        return "Slew"
    return "Unknown"


def _pick_mode_and_lib(
    glob_libs: list[Path], csv_name: str, corner: str | None
) -> tuple[str, Path | None]:
    """Select the lib matching BOTH the csv's corner and its timing type.

    The lib MUST belong to the same corner as the FMC golden data. Joining a
    corner's data against another corner's lib silently produces meaningless
    pass rates (observed: ~44% nominal mismatch when 0p465v data was compared to
    the 0p450v lib). Corner matching is therefore mandatory: when no lib matches
    the corner we return ``None`` so the caller records a loud failure instead of
    falling back to an unrelated lib.
    """

    mode = _mode_for_csv(csv_name)
    if mode == "Unknown" or corner is None:
        return mode, None

    corner_libs = [lf for lf in glob_libs if corner in lf.name]
    if not corner_libs:
        return mode, None

    if mode == "Hold":
        for lf in corner_libs:
            if lf.name.endswith(".cons.lib"):
                return mode, lf
        return mode, None

    # Delay / Slew use the non-constraint lib.
    for lf in corner_libs:
        if "non_cons.lib" in lf.name:
            return mode, lf
    return mode, None


def run_lib_join_sigma(config: CertDataProcessConfig) -> SigmaLibJoinResult:
    started_at = _utc_now()
    t0 = time.monotonic()

    output_dir = config.output_dir.resolve()
    normalized_dir = (output_dir / "normalized" / "fmc").resolve()
    combined_dir = (output_dir / "combined" / "sigma").resolve()
    combined_dir.mkdir(parents=True, exist_ok=True)

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "2-data_process/Combine_Lib_and_FMC/Combine_FMC_and_CDNS_lib.py").resolve()
    tcl = (repo_root / "2-data_process/Combine_Lib_and_FMC/run_ldbx.tcl").resolve()

    logs_dir = (output_dir / "logs").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_log = logs_dir / "lib_join_sigma.log"

    if not normalized_dir.is_dir():
        stage = {
            "stage": "lib_join_sigma",
            "pipeline": "sigma",
            "status": "skipped",
            "reason": "missing_normalized_fmc_dir",
            "started_at_utc": started_at,
            "ended_at_utc": _utc_now(),
            "duration_seconds": round(time.monotonic() - t0, 6),
            "processed": [],
            "failures": [],
        }
        return SigmaLibJoinResult(stage, {"stage": "lib_join_sigma", "status": "not_evaluated", "reason": "No normalized FMC inputs."})

    csv_files = sorted(normalized_dir.glob("fmc_result_*.csv"))
    if not csv_files:
        stage = {
            "stage": "lib_join_sigma",
            "pipeline": "sigma",
            "status": "skipped",
            "reason": "no_fmc_csv_inputs",
            "started_at_utc": started_at,
            "ended_at_utc": _utc_now(),
            "duration_seconds": round(time.monotonic() - t0, 6),
            "processed": [],
            "failures": [],
        }
        return SigmaLibJoinResult(stage, {"stage": "lib_join_sigma", "status": "not_evaluated", "reason": "No normalized FMC CSV inputs."})

    lib_files = sorted(config.lib_dir.resolve().glob("*.lib"))
    processed: list[dict[str, Any]] = []

    if not lib_files:
        stage = {
            "stage": "lib_join_sigma",
            "pipeline": "sigma",
            "status": "skipped",
            "reason": "no_lib_inputs",
            "started_at_utc": started_at,
            "ended_at_utc": _utc_now(),
            "duration_seconds": round(time.monotonic() - t0, 6),
            "processed": [],
            "failures": [],
            "output_dir": str(combined_dir),
        }
        return SigmaLibJoinResult(stage, {"stage": "lib_join_sigma", "status": "not_evaluated", "reason": "No .lib files found in --lib-dir; stage skipped."})

    failures: list[dict[str, Any]] = []
    log_lines: list[str] = [
        "stage=lib_join_sigma",
        f"started_at_utc={started_at}",
        f"normalized_dir={normalized_dir}",
        f"combined_dir={combined_dir}",
        f"lib_dir={config.lib_dir}",
        f"liberate_in_path={bool(shutil.which('liberate'))}",
        "",
        "expected_liberate_env_hint:",
        "  source /tools/dotfile_new/cshrc.liberate 23.1.3.028.isr3",
        "  setenv ALTOS_MEMORY_OPTIMIZATION_OFF 1",
        "",
    ]

    requested_corners = tuple(config.corners)
    libs_have_corner = {c: any(c in lf.name for lf in lib_files) for c in requested_corners}
    log_lines.append("lib_corner_coverage:")
    for c in requested_corners:
        log_lines.append(f"  corner={c} lib_present={libs_have_corner[c]}")
    missing_corner_libs = [c for c in requested_corners if not libs_have_corner[c]]
    if missing_corner_libs:
        log_lines.append(
            "WARNING: no lib in --lib-dir for corner(s): " + ", ".join(missing_corner_libs)
        )
        log_lines.append(
            "  -> those corners will be reported as failures, NOT joined against a wrong-corner lib."
        )
    log_lines.append("")

    for csv_path in csv_files:
        corner = _corner_for_csv(csv_path.name, requested_corners)
        mode = _mode_for_csv(csv_path.name)

        if corner is None:
            failures.append({
                "csv": str(csv_path),
                "reason": "unrecognized_corner",
                "detail": f"CSV name matches none of the requested corners: {list(requested_corners)}",
            })
            continue
        if mode == "Unknown":
            failures.append({
                "csv": str(csv_path),
                "corner": corner,
                "reason": "unknown_type",
                "detail": "CSV name does not end with _delay/_slew/_hold",
            })
            continue

        _, lib_file = _pick_mode_and_lib(lib_files, csv_path.name, corner)
        if lib_file is None:
            if not libs_have_corner.get(corner, False):
                reason = "no_lib_for_corner"
                detail = (
                    f"No .lib in --lib-dir matches corner '{corner}'. Provide this corner's "
                    f"lib; data was NOT joined against a wrong-corner lib (silent mismatch avoided)."
                )
            else:
                reason = "no_lib_for_type"
                detail = (
                    f"Corner '{corner}' lib present but no {mode} lib "
                    f"({'.cons.lib' if mode == 'Hold' else 'non_cons.lib'}) found."
                )
            failures.append({
                "csv": str(csv_path),
                "corner": corner,
                "mode": mode,
                "reason": reason,
                "detail": detail,
            })
            log_lines.append(f"FAIL csv={csv_path.name} corner={corner} mode={mode} reason={reason}")
            continue

        csv_path = csv_path.resolve()
        lib_file = lib_file.resolve()
        cmd = _build_liberate_cmd(tcl=tcl, script=script, lib_file=lib_file, csv_path=csv_path, mode=mode)
        shell_cmd = _build_liberate_shell_cmd(tcl=tcl, script=script, lib_file=lib_file, csv_path=csv_path, mode=mode)

        try:
            proc = subprocess.run(["csh", "-fc", shell_cmd], cwd=str(combined_dir), capture_output=True, text=True)
        except FileNotFoundError:
            stage = {
                "stage": "lib_join_sigma",
                "pipeline": "sigma",
                "status": "skipped",
                "reason": "liberate_not_found",
                "started_at_utc": started_at,
                "ended_at_utc": _utc_now(),
                "duration_seconds": round(time.monotonic() - t0, 6),
                "processed": processed,
                "failures": [],
                "log_file": str(run_log),
                "output_dir": str(combined_dir),
            }
            log_lines.extend(
                [
                    "liberate_not_found=1",
                    "action=source /tools/dotfile_new/cshrc.liberate 23.1.3.028.isr3",
                    "action=setenv ALTOS_MEMORY_OPTIMIZATION_OFF 1",
                ]
            )
            run_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
            return SigmaLibJoinResult(stage, {"stage": "lib_join_sigma", "status": "not_evaluated", "reason": "liberate executable not available in environment."})
        processed.append(
            {
                "csv": str(csv_path),
                "lib": str(lib_file),
                "mode": mode,
                "exit_code": proc.returncode,
                "cmd": shell_cmd,
            }
        )
        log_lines.append(f"CMD: {shell_cmd}")
        log_lines.append(f"EXIT: {proc.returncode}")
        if proc.stdout:
            log_lines.append("STDOUT:")
            log_lines.append(proc.stdout)
        if proc.stderr:
            log_lines.append("STDERR:")
            log_lines.append(proc.stderr)
        log_lines.append("-" * 60)

        if proc.returncode != 0:
            failures.append(
                {
                    "csv": str(csv_path),
                    "reason": "lib_join_failed",
                    "detail": f"liberate exited with {proc.returncode}",
                }
            )

    log_lines.extend(
        [
            "",
            "summary:",
            f"processed_count={len(processed)}",
            f"failure_count={len(failures)}",
        ]
    )
    if failures:
        log_lines.append("failure_reasons:")
        for failure in failures:
            log_lines.append(
                f"  - csv={failure.get('csv')} reason={failure.get('reason')} detail={failure.get('detail', '')}"
            )

    run_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    has_partial_success = bool(processed and failures)
    if has_partial_success:
        status = "partial"
    elif failures:
        status = "failed"
    else:
        status = "passed"

    stage = {
        "stage": "lib_join_sigma",
        "pipeline": "sigma",
        "status": status,
        "started_at_utc": started_at,
        "ended_at_utc": _utc_now(),
        "duration_seconds": round(time.monotonic() - t0, 6),
        "processed": processed,
        "failures": failures,
        "failure_summary": {"count": len(failures), "has_partial_success": has_partial_success},
        "log_file": str(run_log),
        "output_dir": str(combined_dir),
    }
    return SigmaLibJoinResult(
        stage,
        {
            "stage": "lib_join_sigma",
            "status": "not_evaluated",
            "reason": "Legacy lib-join output parity should be validated by RPT diff against legacy flow.",
        },
    )
