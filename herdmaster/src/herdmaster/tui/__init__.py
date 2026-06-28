"""HerdMaster observability TUI (FR-501..505).

Exposes :class:`DashboardApp`, a read-only, real-time terminal dashboard that
renders five live panels (agents, tasks, projects, alerts, metrics) sourced
from the committed ``db``, ``bus``, and ``config`` modules.

The dashboard degrades gracefully across three rendering backends:

* ``textual`` — full interactive TUI when the package is installed.
* ``rich`` — a ``rich.live`` refreshing view when only ``rich`` is present.
* plaintext — a dependency-free stdlib fallback that works anywhere.

Importing this package never requires ``textual`` or ``rich``; the optional
backends are imported lazily only when actually used.
"""

from __future__ import annotations

from .dashboard import (
    DashboardApp,
    DashboardSnapshot,
    HAS_RICH,
    HAS_TEXTUAL,
    run_dashboard,
)

__all__ = [
    "DashboardApp",
    "DashboardSnapshot",
    "HAS_RICH",
    "HAS_TEXTUAL",
    "run_dashboard",
]
