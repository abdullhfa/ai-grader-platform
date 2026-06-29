"""Reflection agent — detects contradictions between agent opinions."""
from __future__ import annotations

from typing import List

from app.ai_reasoning.reasoning_session import AgentOpinion


def run_reflection_agent(opinions: List[AgentOpinion]) -> AgentOpinion:
    by_id = {o.agent_id: o for o in opinions}
    gameplay = by_id.get("gameplay_agent")
    runtime = by_id.get("runtime_agent")
    integrity = by_id.get("integrity_agent")
    concerns = []
    refs = []

    if gameplay and runtime:
        if gameplay.verdict == "support" and runtime.verdict == "oppose":
            concerns.append("gameplay_support_vs_runtime_oppose")
            refs.extend(gameplay.evidence_refs[:2] + runtime.evidence_refs[:2])
        if gameplay.verdict == "oppose" and runtime.verdict == "support":
            concerns.append("runtime_ok_but_gameplay_weak")

    if integrity and integrity.verdict == "suspicious":
        concerns.append("integrity_suspicious_requires_review")

    if concerns:
        return AgentOpinion(
            agent_id="reflection_agent",
            verdict="uncertain",
            confidence=0.55,
            summary="Agent contradiction detected — reflection required before final decision.",
            evidence_refs=refs,
            concerns=concerns,
        )
    return AgentOpinion(
        agent_id="reflection_agent",
        verdict="support",
        confidence=0.75,
        summary="No critical contradictions across agent opinions.",
        evidence_refs=refs,
    )
