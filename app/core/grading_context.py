"""Submission/batch processing context — mode + profile through the pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.core.grading_profiles import GradingProfile, resolve_grading_profile
from app.grading_mode import GradingMode


@dataclass
class SubmissionProcessingContext:
    grading_mode: GradingMode
    profile: GradingProfile

    @property
    def wire_mode(self) -> str:
        return self.grading_mode.to_wire()

    @property
    def flags(self) -> Dict[str, bool]:
        return dict(self.profile.flags)

    @classmethod
    def from_wire(cls, grading_mode: str | None) -> "SubmissionProcessingContext":
        mode = GradingMode.from_wire(grading_mode)
        return cls(grading_mode=mode, profile=resolve_grading_profile(mode))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "grading_mode": self.wire_mode,
            "grading_mode_label": self.grading_mode.display_label,
            "grading_profile": self.profile.to_metadata(),
        }
