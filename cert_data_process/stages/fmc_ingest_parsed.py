"""Ingest already-parsed FMC golden data into the standard normalized table.

Handles two input modes (the deck-parsing mode stays in fmc_combine_data):
  - parsed_dfds: files already in the DFDS normalized format -> validated + placed
    into normalized/fmc as fmc_result_<node>_<corner>_<type>.csv.
  - parsed_scld: SCLD delay/cons files (multiple types per file) -> adapted via
    fmc_scld_adapter into the same normalized CSVs.

Output is identical to fmc_combine_data, so lib-join onward is unchanged.
"""

from __future__ import annotations

import csv
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cert_data_process.config import CertDataProcessConfig, unit_factor
from cert_data_process.parsers import fmc_scld_adapter as scld

_DELAY_REQUIRED = {"Arc", "MC_Nominal", "MC_Early_Sigma", "MC_Late_Sigma", "Table_Type"}
_HOLD_REQUIRED = {"Arc", "MC_Nominal", "MC_Late_Sigma", "Table_Type"}


@dataclass(frozen=True)
class FmcIngestResult:
    stage_execution: dict[str, Any]
    compatibility_stage_report: dict[str, Any]

    @property
    def failed(self) -> bool:
        return self.stage_execution["status"] == "failed"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _node(config: CertDataProcessConfig) -> str:
    return f"{config.process}_{config.process_version}"


def _result(status, started_at, t0, processed, failures, log_lines, run_log, **extra):
    log_lines += ["", "summary:", f"status={status}", f"processed={len(processed)}", f"failures={len(failures)}"]
    for fa in failures:
        log_lines.append(f"failure: {fa.get('reason')} - {fa.get('detail','')}")
    run_log.parent.mkdir(parents=True, exist_ok=True)
    run_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    stage = {
        "stage": "fmc_combine_data", "pipeline": "sigma", "status": status,
        "started_at_utc": started_at, "ended_at_utc": _utc_now(),
        "duration_seconds": round(time.monotonic() - t0, 6),
        "processed": processed, "failures": failures, "log_file": str(run_log),
    }
    stage.update(extra)
    return FmcIngestResult(stage, {"stage": "fmc_combine_data", "status": "not_evaluated",
                                   "reason": "Parsed-input ingest; parity validated by pass-rate correctness."})


def _apply_vtrc(cands: list, config: CertDataProcessConfig, log_lines: list, ctx: str) -> list:
    """Narrow file candidates by VT/RC token when the user set them.

    Disambiguates a dir holding multiple VT (svt/elvt) or RC (cworst/cbest/...)
    variants. Lenient: if a token matches no candidate (filenames may not carry
    it), fall back to the unfiltered list and log the fallback rather than
    dropping everything.
    """
    out = list(cands)
    for label, token in (("vt", config.vt_type), ("rc", config.rc_type)):
        token = (token or "").strip().lower()
        if not token:
            continue
        narrowed = [p for p in out if token in p.name.lower()]
        if narrowed:
            out = narrowed
        else:
            log_lines.append(f"note: {label}_type='{token}' matched no file for {ctx}; ignoring this filter")
    return out


def _validate_dfds_header(path: Path, type_info: str) -> Optional[str]:
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as fh:
            header = next(csv.reader(fh), [])
    except OSError as exc:
        return f"read_error: {exc}"
    cols = set(header)
    required = _DELAY_REQUIRED if type_info in ("delay", "slew") else _HOLD_REQUIRED
    missing = required - cols
    return f"missing columns {sorted(missing)}" if missing else None


def run_fmc_ingest_parsed(config: CertDataProcessConfig) -> FmcIngestResult:
    started_at = _utc_now()
    t0 = time.monotonic()
    out_dir = config.output_dir.resolve() / "normalized" / "fmc"
    run_log = config.output_dir.resolve() / "logs" / "fmc_combine_data.log"
    node = _node(config)
    in_dir = config.fmc_input_dir
    log_lines = [
        f"stage=fmc_combine_data (parsed-ingest mode={config.fmc_mode})",
        f"started_at_utc={started_at}", f"input_dir={in_dir}", f"node={node}",
        f"requested_corners={','.join(config.corners)}", f"requested_types={','.join(config.types)}", "",
    ]
    processed: list[dict] = []
    failures: list[dict] = []

    if not in_dir or not Path(in_dir).is_dir():
        failures.append({"reason": "missing_input_dir", "detail": f"FMC input dir not found: {in_dir}"})
        return _result("failed", started_at, t0, processed, failures, log_lines, run_log)

    in_dir = Path(in_dir)
    all_files = [p for p in in_dir.iterdir() if p.is_file() and p.suffix.lower() == ".csv"]

    # FMC unit -> ps factor. Default preserves current behavior: SCLD assumes ns
    # (×1000), DFDS assumes ps (×1). A user-declared fmc_unit overrides both.
    scld_scale = unit_factor(config.fmc_unit) if config.fmc_unit else scld.NS_TO_PS
    dfds_factor = unit_factor(config.fmc_unit) if config.fmc_unit else 1.0
    log_lines.append(f"fmc_unit={config.fmc_unit or '(default)'} scld_scale={scld_scale} dfds_factor={dfds_factor}")

    if config.fmc_mode == "parsed_dfds":
        for corner in config.corners:
            for type_info in config.types:
                matches = [p for p in all_files if corner in p.name and type_info in p.name]
                matches = _apply_vtrc(matches, config, log_lines, f"corner={corner} type={type_info}")
                if not matches:
                    failures.append({"corner": corner, "type": type_info, "reason": "no_parsed_file",
                                     "detail": f"No DFDS csv with corner '{corner}' and type '{type_info}'"})
                    continue
                src = matches[0]
                err = _validate_dfds_header(src, type_info)
                if err:
                    failures.append({"corner": corner, "type": type_info, "reason": "bad_header",
                                     "detail": f"{src.name}: {err}"})
                    continue
                out_dir.mkdir(parents=True, exist_ok=True)
                dst = out_dir / f"fmc_result_{node}_{corner}_{type_info}.csv"
                shutil.copyfile(src, dst)
                scld.scale_normalized_mc(dst, dfds_factor)  # ps unless user declared otherwise
                processed.append({"corner": corner, "type": type_info, "src": str(src), "out": str(dst)})
                log_lines.append(f"OK   corner={corner} type={type_info} <- {src.name}")
    else:  # parsed_scld
        def _find(corner, group):  # group: 'delay' or 'cons'
            cands = [p for p in all_files if corner in p.name and p.name.lower().startswith(group)]
            if not cands:
                cands = [p for p in all_files if corner in p.name and group in p.name.lower()]
            cands = _apply_vtrc(cands, config, log_lines, f"corner={corner} group={group}")
            return cands[0] if cands else None

        for corner in config.corners:
            want = set(config.types)
            adapted_cache: dict[str, dict] = {}
            for group, group_types in (("delay", {"delay", "slew"}), ("cons", {"hold", "mpw"})):
                if not (want & group_types):
                    continue
                src = _find(corner, group)
                if src is None:
                    for t in (want & group_types):
                        failures.append({"corner": corner, "type": t, "reason": "no_scld_file",
                                         "detail": f"No SCLD '{group}' file containing corner '{corner}'"})
                    continue
                by_type, warns = scld.adapt_scld_file(src, value_scale=scld_scale)
                for w in warns:
                    log_lines.append(f"warn: {w}")
                adapted_cache[group] = {"src": src, "by_type": by_type}
                for type_info in sorted(want & group_types):
                    rows = by_type.get(type_info)
                    if not rows:
                        failures.append({"corner": corner, "type": type_info, "reason": "no_rows_for_type",
                                         "detail": f"{src.name}: no '{type_info}' rows after filtering"})
                        continue
                    dst = scld.write_normalized(out_dir, node, corner, type_info, rows)
                    processed.append({"corner": corner, "type": type_info, "src": str(src),
                                      "out": str(dst), "rows": len(rows)})
                    log_lines.append(f"OK   corner={corner} type={type_info} rows={len(rows)} <- {src.name}")

    if processed and failures:
        status = "partial"
    elif failures:
        status = "failed"
    else:
        status = "passed"
    return _result(status, started_at, t0, processed, failures, log_lines, run_log)
