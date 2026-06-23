"""Verify bundle-aware pin lookup (multi-bit support) in the lib-join scripts.

The legacy Combine_FMC_and_*_lib.py modules run work at import time, so we can't
import them directly. Instead we extract the real `find_pin_group` source via AST
and exec just that function, then exercise it with fake ldbx group objects.
"""

import ast
from pathlib import Path

import pytest

_SCRIPTS = [
    "cert_data_process/engines/combine/Combine_FMC_and_CDNS_lib.py",
    "cert_data_process/engines/combine/Combine_FMC_and_SNPS_lib.py",
]


def _load_find_pin_group(rel_path):
    src = (Path(__file__).resolve().parents[1] / rel_path).read_text()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "find_pin_group":
            mod = ast.Module(body=[node], type_ignores=[])
            ns = {}
            exec(compile(mod, rel_path, "exec"), ns)
            return ns["find_pin_group"]
    raise AssertionError(f"find_pin_group not found in {rel_path}")


class _Pin:
    def __init__(self, name):
        self.name = name


class _Group:
    """Fake ldbx group: getChildren('pin', name) / getChildren('bundle')."""

    def __init__(self, pins=None, bundles=None):
        self._pins = list(pins or [])
        self._bundles = list(bundles or [])

    def getChildren(self, kind, name=None):
        if kind == "pin":
            return [p for p in self._pins if name is None or p.name == name]
        if kind == "bundle":
            return list(self._bundles)
        return []


@pytest.mark.parametrize("script", _SCRIPTS)
def test_base_cell_pin_direct_child(script):
    find_pin_group = _load_find_pin_group(script)
    cell = _Group(pins=[_Pin("Z"), _Pin("A")])
    assert [p.name for p in find_pin_group(cell, "Z")] == ["Z"]


@pytest.mark.parametrize("script", _SCRIPTS)
def test_mb_cell_pin_inside_bundle(script):
    find_pin_group = _load_find_pin_group(script)
    bundle_q = _Group(pins=[_Pin("Q1"), _Pin("Q2")])
    bundle_d = _Group(pins=[_Pin("D1"), _Pin("D2")])
    cell = _Group(pins=[_Pin("CP")], bundles=[bundle_q, bundle_d])
    assert [p.name for p in find_pin_group(cell, "D1")] == ["D1"]
    assert [p.name for p in find_pin_group(cell, "Q2")] == ["Q2"]
    assert find_pin_group(cell, "CP")[0].name == "CP"  # direct pin still wins


@pytest.mark.parametrize("script", _SCRIPTS)
def test_missing_pin_returns_empty(script):
    find_pin_group = _load_find_pin_group(script)
    cell = _Group(pins=[_Pin("Z")], bundles=[_Group(pins=[_Pin("D1")])])
    assert find_pin_group(cell, "NOPE") == []
