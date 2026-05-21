#!/usr/bin/env python3
"""Byte-compare legacy and new MC aggregated CSV outputs."""

from __future__ import annotations

import argparse
from pathlib import Path


def _paths(root: Path, process: str, process_version: str, corner: str, typ: str) -> Path:
    return root / f"MC_{process}_{process_version}_{corner}_{typ}.csv"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--legacy-root", required=True)
    p.add_argument("--new-root", required=True)
    p.add_argument("--process", required=True)
    p.add_argument("--process-version", required=True)
    p.add_argument("--corners", required=True)
    p.add_argument("--types", default="delay,slew")
    args = p.parse_args()

    legacy_root = Path(args.legacy_root)
    new_root = Path(args.new_root)
    corners = [x.strip() for x in args.corners.split(",") if x.strip()]
    types = [x.strip() for x in args.types.split(",") if x.strip()]

    failures = 0
    for corner in corners:
        for typ in types:
            l = _paths(legacy_root, args.process, args.process_version, corner, typ)
            n = _paths(new_root, args.process, args.process_version, corner, typ)
            if not l.is_file() or not n.is_file():
                print(f"MISSING {corner} {typ}: legacy={l.exists()} new={n.exists()} :: {l} :: {n}")
                failures += 1
                continue
            if l.read_bytes() == n.read_bytes():
                print(f"OK {corner} {typ}")
            else:
                print(f"DIFF {corner} {typ}")
                failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
