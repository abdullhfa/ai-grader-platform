"""Reasoning session models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentOpinion:
    agent_id: str
    verdict: str  # support | oppose | uncertain | suspicious
    confidence: float
    summary: str
    evidence_refs: List[str] = field(default_factory=list)
    concerns: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "summary": self.summary,
            "evidence_refs": self.evidence_refs,
            "concerns": self.concerns,
        }


@dataclass
class FinalDecision:
    decision: str  # supported | rejected | manual_review | insufficient_evidence
    weighted_confidence: float
    requires_manual_review: bool
    reasoning_rejected: bool = False
    agent_opinions: List[AgentOpinion] = field(default_factory=list)
    arbitration_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "weighted_confidence": self.weighted_confidence,
            "requires_manual_review": self.requires_manual_review,
            "reasoning_rejected": self.reasoning_rejected,
            "agent_opinions": [a.to_dict() for a in self.agent_opinions],
            "arbitration_notes": self.arbitration_notes,
        }


@dataclass
class ReasoningSession:
    submission_key: str
    session_id: Optional[str] = None
    criterion_graphs: List[Any] = field(default_factory=list)
    agent_opinions: List[AgentOpinion] = field(default_factory=list)
    final_decisions: Dict[str, FinalDecision] = field(default_factory=dict)
    hallucination_flags: List[Dict[str, Any]] = field(default_factory=list)
    pipeline_version: str = "ai_reasoning_v1"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_version": self.pipeline_version,
            "submission_key": self.submission_key,
            "session_id": self.session_id,
            "criterion_graphs": [
                g.to_dict() if hasattr(g, "to_dict") else g for g in self.criterion_graphs
            ],
            "agent_opinions": [a.to_dict() for a in self.agent_opinions],
            "final_decisions": {k: v.to_dict() for k, v in self.final_decisions.items()},
            "hallucination_flags": self.hallucination_flags,
        }
