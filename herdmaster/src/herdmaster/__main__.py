"""HerdMaster entry point with ADR-001 graceful Herdr boot check."""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)


async def _check_herdr_connection(cfg) -> bool:  # noqa: ANN001
    """Check whether Herdr is reachable by calling agent_list with a 5-second timeout.

    ADR-001 FR-AC-01/02: This is a non-blocking probe performed at startup.
    Returns True if the socket is accessible; False otherwise.
    Never raises — degraded mode is acceptable.
    """
    try:
        from herdmaster.herdr.adapter import HerdrAdapter

        socket_path = str(cfg.herdr.socket_path)
        adapter = HerdrAdapter(socket_path)
        agents = await asyncio.wait_for(adapter.agent_list(), timeout=5.0)
        log.info(
            "herdr_connection_ok",
            extra={"socket": socket_path, "agent_count": len(agents)},
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "herdr_unavailable_degraded_mode",
            extra={"reason": str(exc)},
        )
        return False


def main() -> None:
    try:
        from herdmaster.cli import app

        app()
    except ImportError:
        print("CLI not yet built")


if __name__ == "__main__":
    main()
