"""Canonical grading mode enum — STANDARD (fast) vs PRO (deep)."""
from __future__ import annotations

from enum import Enum


class GradingMode(str, Enum):
    """User-facing modes. Wire/storage still uses fast|deep for backward compatibility."""

    STANDARD = "standard"
    PRO = "pro"

    @classmethod
    def from_wire(cls, value: str | None) -> "GradingMode":
        v = (value or "deep").strip().lower()
        if v in ("fast", "basic", "standard"):
            return cls.STANDARD
        if v in ("deep", "pro"):
            return cls.PRO
        return cls.PRO

    def to_wire(self) -> str:
        """Legacy pipeline value stored in snapshots and batch progress."""
        return "fast" if self is GradingMode.STANDARD else "deep"

    @property
    def display_label(self) -> str:
        return "STANDARD" if self is GradingMode.STANDARD else "PRO"
