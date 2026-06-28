"""Herdr integration boundary for HerdMaster.

Only this package should invoke the Herdr CLI.
"""

from .adapter import HerdrAdapter, HerdrError
from .parser import HerdrAgent, HerdrPane, output_hash, parse_agent_list, parse_pane_list

__all__ = [
    "HerdrAdapter",
    "HerdrError",
    "HerdrAgent",
    "HerdrPane",
    "output_hash",
    "parse_agent_list",
    "parse_pane_list",
]
