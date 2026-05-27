#!/usr/bin/env python3
"""Smoke tests for action_log_writer.ActionLogger.

Uses the built-in _run_self_test() to exercise:
  - tier validation (tier3 must hard-block)
  - hash chain continuity
  - fcntl.flock concurrency
  - canonical_json determinism
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys


SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "action_log_writer.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("action_log_writer", SRC)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_self_test_passes():
    mod = _load_module()
    rc = mod._run_self_test()
    assert rc == 0, f"_run_self_test returned {rc}"


def test_canonical_json_stable_ordering():
    mod = _load_module()
    a = mod.canonical_json({"b": 2, "a": 1})
    b = mod.canonical_json({"a": 1, "b": 2})
    assert a == b


def test_sha256_hex_deterministic():
    mod = _load_module()
    assert mod.sha256_hex("hello") == mod.sha256_hex("hello")
    assert mod.sha256_hex("a") != mod.sha256_hex("b")


def test_valid_tiers_constant():
    mod = _load_module()
    assert "tier0" in mod.VALID_TIERS
    assert "tier3" in mod.VALID_TIERS
    assert "tier99" not in mod.VALID_TIERS
