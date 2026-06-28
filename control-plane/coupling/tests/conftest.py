"""Test path setup for coupling tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERDMASTER_SRC = ROOT.parents[1] / "HerdMaster" / "src"

for path in (ROOT, HERDMASTER_SRC):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)
