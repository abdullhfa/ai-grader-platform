"""Integrity agent — plagiarism / mismatch heuristics."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.ai_reasoning.reasoning_session import AgentOpinion


def run_integrity_agent(
    artifact_inventory: Optional[Dict[str, Any]],
    grading_result: Optional[Dict[str, Any]] = None,
) -> AgentOpinion:
    inventory = artifact_inventory or {}
    grading = grading_result or {}
    concerns = []
    refs = []

    consistency = inventory.get("cross_artifact_consistency") or {}
    ambiguities = consistency.get("ambiguities") or []
    if ambiguities:
        concerns.extend([str(a.get("code") or "ambiguity") for a in ambiguities[:4]])

    ai_likelihood = float(grading.get("ai_likelihood") or 0)
    if ai_likelihood >= 75:
        concerns.append("high_ai_likelihood_text")
        refs.append("integrity:ai_likelihood_high")

    alignment = (inventory.get("runtime_artifacts") or {}).get("unity_source_build_alignment")
    if alignment == "source_without_build":
        concerns.append("unity_source_without_build")
        refs.append("integrity:source_build_mismatch")

    if concerns:
        return AgentOpinion(
            agent_id="integrity_agent",
            verdict="suspicious" if ai_likelihood >= 75 else "uncertain",
            confidence=0.7,
            summary="Integrity signals require human review.",
            evidence_refs=refs,
            concerns=concerns,
        )
    return AgentOpinion(
        agent_id="integrity_agent",
        verdict="support",
        confidence=0.8,
        summary="No major integrity flags in artifact cross-check.",
        evidence_refs=refs,
    )
