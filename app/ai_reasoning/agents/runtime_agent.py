"""Runtime agent — stability, crash, telemetry."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.ai_reasoning.reasoning_session import AgentOpinion


def run_runtime_agent(
    artifact_inventory: Optional[Dict[str, Any]],
    gameplay_analysis: Optional[Dict[str, Any]] = None,
) -> AgentOpinion:
    inventory = artifact_inventory or {}
    obs = inventory.get("runtime_observation_report") or {}
    telemetry = (gameplay_analysis or {}).get("telemetry") or obs.get("runtime_metrics") or {}
    refs = []
    concerns = []

    if obs.get("runtime_observed"):
        refs.append("runtime:observed")
    if obs.get("crash_detected") or telemetry.get("crash_detected"):
        concerns.append("crash_detected")
        refs.append("runtime:crash")
        return AgentOpinion(
            agent_id="runtime_agent",
            verdict="oppose",
            confidence=0.9,
            summary="Runtime crash detected — stability concern.",
            evidence_refs=refs,
            concerns=concerns,
        )
    if telemetry.get("freeze_detected"):
        concerns.append("freeze_detected")
        return AgentOpinion(
            agent_id="runtime_agent",
            verdict="oppose",
            confidence=0.82,
            summary="Runtime freeze detected in telemetry.",
            evidence_refs=refs,
            concerns=concerns,
        )
    if obs.get("runtime_observed"):
        fps = telemetry.get("avg_fps")
        summary = "Runtime launch observed with stable smoke session."
        if fps:
            summary += f" Avg FPS hint: {fps}."
        return AgentOpinion(
            agent_id="runtime_agent",
            verdict="support",
            confidence=0.88,
            summary=summary,
            evidence_refs=refs,
        )
    return AgentOpinion(
        agent_id="runtime_agent",
        verdict="uncertain",
        confidence=0.4,
        summary="No runtime observation artifacts.",
        evidence_refs=refs,
        concerns=["no_runtime_observation"],
    )
