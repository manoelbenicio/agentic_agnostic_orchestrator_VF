"""Pytest import path setup for orchestrator tests."""

from __future__ import annotations

import sys
from pathlib import Path

CONTROL_PLANE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CONTROL_PLANE_ROOT))

