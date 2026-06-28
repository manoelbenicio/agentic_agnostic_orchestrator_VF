from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().with_name("f7_harness.py")
SPEC = importlib.util.spec_from_file_location("f7_harness", MODULE_PATH)
assert SPEC and SPEC.loader
f7_harness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = f7_harness
SPEC.loader.exec_module(f7_harness)


def test_plan_profile_lists_all_checks_without_network() -> None:
    checks = f7_harness.selected_checks("plan")
    assert {check.check_id for check in checks} >= {
        "f7.g1.health",
        "f7.g3.ui_routes",
        "f7.g6.perf_smoke",
        "f7.g7.a11y_smoke",
        "f7.g2.api_contracts",
    }

    results = f7_harness.plan_results(checks)
    assert all(item.status == "planned" for item in results)
    assert all(item.duration_ms == 0 for item in results)


def test_exhaustive_profile_requires_explicit_opt_in() -> None:
    with pytest.raises(f7_harness.HarnessError, match="requires --allow-exhaustive"):
        f7_harness.selected_checks("exhaustive")

    checks = f7_harness.selected_checks("exhaustive", allow_exhaustive=True)
    assert any(check.exhaustive for check in checks)


def test_smoke_profile_excludes_full_and_exhaustive_checks() -> None:
    checks = f7_harness.selected_checks("smoke")
    assert checks
    assert all(check.profile == "smoke" for check in checks)
    assert not any(check.exhaustive for check in checks)
