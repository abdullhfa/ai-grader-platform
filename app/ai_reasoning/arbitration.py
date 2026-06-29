"""Agent opinion arbitration."""
from __future__ import annotations

from typing import List

from app.ai_reasoning.confidence_engine import arbitrate_confidence
from app.ai_reasoning.reasoning_session import AgentOpinion, FinalDecision


def arbitrate_opinions(
    opinions: List[AgentOpinion],
    *,
    graph_confidence: float = 0.5,
) -> FinalDecision:
    notes: List[str] = []
    verdicts = {o.verdict for o in opinions}
    suspicious = any(o.verdict == "suspicious" for o in opinions)
    oppose = any(o.verdict == "oppose" for o in opinions)
    support = any(o.verdict == "support" for o in opinions)

    agent_confidences = [o.confidence for o in opinions]
    weighted = arbitrate_confidence(graph_confidence, agent_confidences)

    requires_manual = False
    decision = "insufficient_evidence"

    if suspicious:
        decision = "manual_review"
        requires_manual = True
        notes.append("integrity_agent_flagged_suspicious")
    elif oppose and support:
        decision = "manual_review"
        requires_manual = True
        notes.append("agent_disagreement_requires_review")
    elif support and weighted >= 0.65:
        decision = "supported"
    elif oppose:
        decision = "rejected"
        notes.append("agents_oppose_with_evidence")
    elif weighted < 0.45:
        decision = "insufficient_evidence"
        notes.append("low_weighted_confidence")

    return FinalDecision(
        decision=decision,
        weighted_confidence=weighted,
        requires_manual_review=requires_manual,
        agent_opinions=opinions,
        arbitration_notes=notes,
    )
