"""Exponential backoff with jitter for rate-limit responses."""

from __future__ import annotations

from dataclasses import dataclass
from random import Random


@dataclass(frozen=True, slots=True)
class BackoffPolicy:
    """Backoff policy for retrying 429/503 vendor responses."""

    base_seconds: float = 1.0
    max_seconds: float = 60.0
    jitter_ratio: float = 0.2

    def delay(self, attempt: int, *, rng: Random | None = None) -> float:
        """Return exponential delay plus bounded jitter for a 1-based attempt."""
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        base = min(self.max_seconds, self.base_seconds * (2 ** (attempt - 1)))
        if self.jitter_ratio <= 0:
            return base
        random = rng or Random()
        jitter = base * self.jitter_ratio * random.random()
        return min(self.max_seconds, base + jitter)

