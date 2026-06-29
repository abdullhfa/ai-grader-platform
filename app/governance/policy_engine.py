"""Institutional policy rules — mandatory review, escalation triggers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from app.governance.replay_viewer import ReplayInspectionBundle


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    condition: str
    action: str
    description: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "rule_id": self.rule_id,
            "condition": self.condition,
            "action": self.action,
            "description": self.description,
        }


DEFAULT_POLICIES: tuple[PolicyRule, ...] = (
    PolicyRule(
        "integrity_high",
        "integrity_suspicion > 0.8",
        "mandatory_manual_review",
        "High integrity suspicion requires human review",
    ),
    PolicyRule(
        "hallucination_rejected",
        "reasoning_rejected == true",
        "mandatory_manual_review",
        "Hallucination guard rejection requires examiner",
    ),
    PolicyRule(
        "low_confidence",
        "graph_confidence < 0.5",
        "escalate_to_senior",
        "Low evidence confidence escalates to senior examiner",
    ),
    PolicyRule(
        "contradiction_detected",
        "contradictions_count > 0",
        "mandatory_manual_review",
        "Agent contradictions require replay review",
    ),
    PolicyRule(
        "manual_review_flag",
        "requires_manual_review == true",
        "mandatory_manual_review",
        "AI arbitration flagged manual review",
    ),
)


def _eval_condition(condition: str, ctx: Dict[str, Any]) -> bool:
    """Safe minimal condition evaluator for governance rules."""
    cond = condition.strip()
    if ">" in cond:
        left, right = [p.strip() for p in cond.split(">", 1)]
        try:
            return float(ctx.get(left, 0)) > float(right)
        except (TypeError, ValueError):
            return False
    if "<" in cond:
        left, right = [p.strip() for p in cond.split("<", 1)]
        try:
            return float(ctx.get(left, 0)) < float(right)
        except (TypeError, ValueError):
            return False
    if "==" in cond:
        left, right = [p.strip() for p in cond.split("==", 1)]
        val = ctx.get(left)
        if right.lower() == "true":
            return bool(val) is True
        if right.lower() == "false":
            return bool(val) is False
        return str(val) == right
    return False


def build_policy_context(
    bundle: ReplayInspectionBundle,
    grading_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    final = (bundle.ai_reasoning or {}).get("final_decision") or {}
    integrity = (grading_result or {}).get("integrity") or {}
    return {
        "integrity_suspicion": float(integrity.get("suspicion_score") or integrity.get("score") or 0),
        "reasoning_rejected": bool(final.get("reasoning_rejected")),
        "graph_confidence": float(final.get("confidence") or bundle.confidence_scores.get("graph_confidence") or 0),
        "contradictions_count": len(bundle.contradictions),
        "requires_manual_review": bool(final.get("requires_manual_review")),
    }


def evaluate_policies(
    bundle: ReplayInspectionBundle,
    grading_result: Optional[Dict[str, Any]] = None,
    *,
    rules: Optional[List[PolicyRule]] = None,
) -> Dict[str, Any]:
    ctx = build_policy_context(bundle, grading_result)
    triggered: List[Dict[str, str]] = []
    actions: List[str] = []

    for rule in rules or list(DEFAULT_POLICIES):
        if _eval_condition(rule.condition, ctx):
            triggered.append(rule.to_dict())
            if rule.action not in actions:
                actions.append(rule.action)

    return {
        "context": ctx,
        "triggered_rules": triggered,
        "required_actions": actions,
        "mandatory_manual_review": "mandatory_manual_review" in actions,
        "escalate_to_senior": "escalate_to_senior" in actions,
    }
