#!/usr/bin/env python3
"""Compare legacy vs new FMC CSV outputs with byte-level equality checks.

This helper is intended for the PR2 workflow where users already generated
legacy `calculate.py` CSV outputs and new `cert_data_process` CSV outputs, then
want a fast pass/fail report across all corner/type combinations.
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class FileComparison:
    corner: str
    type_name: str
    legacy_path: Path
    new_path: Path
    status: str
    detail: str


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _node(process: str, process_version: str) -> str:
    return f"{process}_{process_version}"


def _csv_name(process: str, process_version: str, corner: str, type_name: str) -> str:
    return f"fmc_result_{_node(process, process_version)}_{corner}_{type_name}.csv"


def _compare_one(legacy_path: Path, new_path: Path, corner: str, type_name: str) -> FileComparison:
    if not legacy_path.is_file():
        return FileComparison(corner, type_name, legacy_path, new_path, "missing", "legacy file missing")
    if not new_path.is_file():
        return FileComparison(corner, type_name, legacy_path, new_path, "missing", "new file missing")

    legacy_bytes = legacy_path.read_bytes()
    new_bytes = new_path.read_bytes()
    if legacy_bytes == new_bytes:
        digest = _sha256(legacy_path)
        return FileComparison(corner, type_name, legacy_path, new_path, "equal", f"sha256={digest}")

    return FileComparison(
        corner,
        type_name,
        legacy_path,
        new_path,
        "diff",
        f"legacy_sha256={_sha256(legacy_path)} new_sha256={_sha256(new_path)}",
    )


def _parse_csv_list(value: str) -> list[str]:
    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items:
        raise argparse.ArgumentTypeError("value must contain at least one comma-separated item")
    return items


def run(
    legacy_root: Path,
    new_root: Path,
    process: str,
    process_version: str,
    corners: Iterable[str],
    types: Iterable[str],
) -> int:
    results: list[FileComparison] = []

    for corner in corners:
        for type_name in types:
            csv_name = _csv_name(process, process_version, corner, type_name)
            legacy_path = legacy_root / corner / type_name / csv_name
            new_path = new_root / corner / type_name / csv_name
            results.append(_compare_one(legacy_path, new_path, corner, type_name))

    passed = [item for item in results if item.status == "equal"]
    failed = [item for item in results if item.status != "equal"]

    print("Byte-equality comparison report")
    print(f"legacy_root={legacy_root}")
    print(f"new_root={new_root}")
    print(f"total={len(results)} pass={len(passed)} fail={len(failed)}")
    print("")

    for item in results:
        icon = "PASS" if item.status == "equal" else "FAIL"
        print(f"[{icon}] corner={item.corner} type={item.type_name} :: {item.detail}")
        if item.status != "equal":
            print(f"       legacy={item.legacy_path}")
            print(f"       new   ={item.new_path}")

    if failed:
        print("\nResult: NOT byte-equal across all requested files.")
        return 1

    print("\nResult: All requested files are byte-equal.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare legacy/new FMC CSV files by raw bytes.")
    parser.add_argument("--legacy-root", required=True, type=Path, help="Root directory for legacy CSV folders.")
    parser.add_argument("--new-root", required=True, type=Path, help="Root directory for new CSV folders.")
    parser.add_argument("--process", required=True, help="Process name, e.g. n2p.")
    parser.add_argument("--process-version", required=True, help="Process version, e.g. v1p0.")
    parser.add_argument("--corners", required=True, type=_parse_csv_list, help="Comma-separated corners list.")
    parser.add_argument("--types", default="delay,slew,hold", type=_parse_csv_list, help="Comma-separated types list.")
    args = parser.parse_args()

    return run(
        legacy_root=args.legacy_root,
        new_root=args.new_root,
        process=args.process,
        process_version=args.process_version,
        corners=args.corners,
        types=args.types,
    )


if __name__ == "__main__":
    raise SystemExit(main())
