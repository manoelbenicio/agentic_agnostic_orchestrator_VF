from .base import NativeAgentAdapter
from .codex import CodexAdapter
from .kiro import KiroAdapter
from .antigravity import AntigravityAdapter
from .gemini import GeminiAdapter
from .scrape_adapter import ScreenScrapeAdapter
from .scrape_models import (
    Confidence,
    ParsedSignal,
    ScrapeDetectionConfig,
    SignalKind,
    TerminalSnapshot,
)
from .scrape_parser import TerminalOutputParser
from .scrape_patterns import (
    TerminalPattern,
    detect_vendor,
    get_all_patterns,
    get_patterns,
    list_vendors,
)

__all__ = [
    # Base
    "NativeAgentAdapter",
    # Native adapters
    "AntigravityAdapter",
    "CodexAdapter",
    "GeminiAdapter",
    "KiroAdapter",
    # Screen-scrape fallback
    "ScreenScrapeAdapter",
    "TerminalOutputParser",
    # Models
    "Confidence",
    "ParsedSignal",
    "ScrapeDetectionConfig",
    "SignalKind",
    "TerminalPattern",
    "TerminalSnapshot",
    # Pattern utilities
    "detect_vendor",
    "get_all_patterns",
    "get_patterns",
    "list_vendors",
]
