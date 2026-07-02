"""Analysis profiles for STANDARD vs PRO — evidence depth only; governance is shared."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from app.grading_mode import GradingMode
from app.grading_mode_policy import (
    BASIC_MAX_VIDEO_KEYFRAMES,
    BASIC_MAX_VIDEOS,
    PRO_MAX_VISION_IMAGES,
    basic_max_vision_images,
    deep_grading_flags,
    fast_grading_flags,
    grading_mode_display_label,
)


PROFILE_VERSION = "grading_profile_v1"


@dataclass(frozen=True)
class GradingProfile:
    version: str
    mode: GradingMode
    mode_label: str
    runtime_enabled: bool
    runtime_depth: str  # fast | deep
    gameplay_agent: bool
    ai_reasoning: bool
    document_analysis: str  # fast | deep
    image_analysis: str  # basic | deep
    video_analysis: str  # sampled | deep
    evidence_depth: str  # summary | detailed
    max_runtime_seconds: int
    max_images: int
    max_video_keyframes: int
    governance_shared: bool = True
    flags: Dict[str, bool] = field(default_factory=dict)

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "profile_version": self.version,
            "mode": self.mode.value,
            "mode_label": self.mode_label,
            "runtime_enabled": self.runtime_enabled,
            "runtime_depth": self.runtime_depth,
            "gameplay_agent_used": self.gameplay_agent,
            "ai_reasoning": self.ai_reasoning,
            "document_analysis": self.document_analysis,
            "image_analysis": self.image_analysis,
            "video_analysis": self.video_analysis,
            "evidence_depth": self.evidence_depth,
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_images": self.max_images,
            "max_video_keyframes": self.max_video_keyframes,
            "governance_shared": self.governance_shared,
            "explanation_strategy": (
                "template" if self.mode is GradingMode.STANDARD else "template+ai_polish"
            ),
        }


_std_flags = fast_grading_flags("fast")
_pro_flags = deep_grading_flags("deep")

STANDARD_PROFILE = GradingProfile(
    version=PROFILE_VERSION,
    mode=GradingMode.STANDARD,
    mode_label="STANDARD",
    runtime_enabled=not _std_flags["skip_runtime_observation"],
    runtime_depth="fast",
    gameplay_agent=False,
    ai_reasoning=not _std_flags["skip_ai_evidence_reasoning"],
    document_analysis="fast",
    image_analysis="basic",
    video_analysis="sampled",
    evidence_depth="summary",
    max_runtime_seconds=30,
    max_images=basic_max_vision_images(),
    max_video_keyframes=BASIC_MAX_VIDEO_KEYFRAMES * BASIC_MAX_VIDEOS,
    flags=_std_flags,
)

PRO_PROFILE = GradingProfile(
    version=PROFILE_VERSION,
    mode=GradingMode.PRO,
    mode_label="PRO",
    runtime_enabled=not _pro_flags["skip_runtime_observation"],
    runtime_depth="deep",
    gameplay_agent=bool(
        _pro_flags.get("enable_web_browser_automation")
        or _pro_flags.get("enable_gamemaker_runtime_verification")
        or _pro_flags.get("enable_scratch_runtime_verification")
    ),
    ai_reasoning=not _pro_flags["skip_ai_evidence_reasoning"],
    document_analysis="deep",
    image_analysis="deep",
    video_analysis="deep",
    evidence_depth="detailed",
    max_runtime_seconds=120,
    max_images=PRO_MAX_VISION_IMAGES,
    max_video_keyframes=25,
    flags=_pro_flags,
)


def resolve_grading_profile(mode: GradingMode | str | None) -> GradingProfile:
    if isinstance(mode, GradingMode):
        return STANDARD_PROFILE if mode is GradingMode.STANDARD else PRO_PROFILE
    resolved = GradingMode.from_wire(str(mode) if mode else None)
    return STANDARD_PROFILE if resolved is GradingMode.STANDARD else PRO_PROFILE


def attach_grading_mode_metadata(
    payload: Dict[str, Any],
    grading_mode: str | None,
) -> Dict[str, Any]:
    """Persist mode + profile audit fields on grading snapshots."""
    mode = GradingMode.from_wire(grading_mode)
    profile = resolve_grading_profile(mode)
    out = dict(payload)
    out["grading_mode"] = mode.to_wire()
    out["grading_mode_label"] = grading_mode_display_label(mode.to_wire())
    meta = profile.to_metadata()
    inv = out.get("artifact_inventory") if isinstance(out.get("artifact_inventory"), dict) else {}
    rt = inv.get("runtime_observation_report") or out.get("runtime_observation_report") or {}
    if isinstance(rt, dict):
        rt_status = str(rt.get("status") or "")
        meta["runtime_attempted"] = rt_status in (
            "completed",
            "partial",
            "error",
        ) and rt_status not in ("skipped_fast_mode", "gated", "no_artifacts", "skipped")
        if rt.get("runtime_depth"):
            meta["runtime_depth"] = rt.get("runtime_depth")
    try:
        from app.gameplay_verifier import build_gameplay_verification_summary

        gv = build_gameplay_verification_summary(
            rt if isinstance(rt, dict) else None,
            inventory=inv,
            grading_result=out,
        )
        meta["gameplay_evidence_level"] = gv.get("evidence_level")
        meta["agent_play_label_ar"] = gv.get("agent_play_label_ar")
        meta["gameplay_agent_used"] = gv.get("gameplay_agent_used")
        meta["runtime_verified"] = gv.get("runtime_verified")
        meta["l4_level"] = gv.get("l4_level")
        meta["automated_l4_gate"] = gv.get("automated_l4_gate")
    except Exception:
        pass
    out["grading_profile"] = meta
    return out
