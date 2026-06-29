"""
Evidence Strength model — the governing principle of the grader.

Shift from a binary "presence == proof" view to "proof measured by a confidence
degree". Every criterion carries an ``evidence_strength_score`` in [0, 1] and a
``decision_confidence`` band. This lets the orchestration concentrate the heavy /
slow verification (live runtime, ensemble, human flag) ONLY on low-confidence
criteria, keeping the common Pass path fast.

This module is deliberately pure (no I/O, no AI calls) so it is deterministic and
trivially testable.

Key idea for closed/Linux engines (GameMaker, Scratch, Unity exports):
  executable_present   < gameplay_video_verified < runtime_observed
A gameplay video analysed deterministically is treated as an *equivalent* runtime
evidence source for execution criteria (P5/P6/P7/M3), not a second-class fallback.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

EVIDENCE_STRENGTH_VERSION = "evidence_strength_v1"

# Weight that each evidence tier contributes toward an *execution / runtime* claim.
# These are the strongest contribution a single tier can make on its own (0..1).
TIER_WEIGHTS: Dict[str, float] = {
    "source_present": 0.35,          # code/project exists, never executed
    "screenshots_only": 0.30,        # static screenshots claiming runtime
    "executable_present": 0.55,      # a build exists (exe/apk/data.win/.sb3) but unobserved
    "gameplay_video_verified": 0.80, # deterministic video signals corroborated by source
    "runtime_observed": 0.95,        # live sandbox actually ran the build
}

# Small additive corroboration bonuses (capped so no combination exceeds 1.0).
_CORROBORATION_BONUS: Dict[str, float] = {
    "source_present": 0.06,
    "screenshots_only": 0.03,
    "executable_present": 0.05,
    "gameplay_video_verified": 0.05,
    "testing_evidence": 0.05,
}

# Command-verb depth (Bloom-like). Higher verbs demand stronger evidence before we
# can be confident a criterion is genuinely achieved.
COMMAND_VERB_DEPTH: Dict[str, int] = {
    # Level 1 — recall
    "state": 1, "identify": 1, "list": 1, "name": 1, "label": 1, "define": 1,
    # Level 2 — comprehension
    "describe": 2, "outline": 2, "summarise": 2, "summarize": 2, "explain": 2,
    # Level 3 — application / production
    "demonstrate": 3, "produce": 3, "implement": 3, "create": 3, "develop": 3,
    "build": 3, "use": 3, "apply": 3, "modify": 3,
    # Level 4 — analysis
    "analyse": 4, "analyze": 4, "compare": 4, "examine": 4, "investigate": 4,
    "assess": 4, "review": 4,
    # Level 5 — evaluation / synthesis
    "evaluate": 5, "justify": 5, "critically": 5, "recommend": 5, "optimise": 5,
    "optimize": 5, "validate": 5,
}

# Minimum evidence_strength_score we expect for a criterion to read as "confidently
# achieved", indexed by command-verb depth. Deeper verbs require stronger proof.
_DEPTH_REQUIRED_STRENGTH: Dict[int, float] = {
    1: 0.30,
    2: 0.45,
    3: 0.60,
    4: 0.75,
    5: 0.85,
}

# Decision-confidence bands derived from the score gap vs. the required threshold.
_HIGH_CONFIDENCE_MARGIN = 0.15
_LOW_CONFIDENCE_MARGIN = 0.10


@dataclass
class EvidenceProfile:
    """Boolean/observational facts about what a submission actually provides."""

    source_present: bool = False
    executable_present: bool = False
    gameplay_video_verified: bool = False
    runtime_observed: bool = False
    screenshots_only: bool = False
    testing_evidence: bool = False
    extras: Dict[str, Any] = field(default_factory=dict)

    def active_tiers(self) -> List[str]:
        tiers: List[str] = []
        for tier in (
            "runtime_observed",
            "gameplay_video_verified",
            "executable_present",
            "source_present",
            "screenshots_only",
        ):
            if getattr(self, tier, False):
                tiers.append(tier)
        return tiers


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return round(value, 4)


def compute_evidence_strength_score(profile: EvidenceProfile) -> Dict[str, Any]:
    """Collapse an :class:`EvidenceProfile` into a measured strength score.

    Strategy: take the strongest tier present as the base, then add capped
    corroboration bonuses for every *other* corroborating tier. This rewards
    multiple independent evidence sources without ever letting weak signals alone
    masquerade as strong proof.
    """
    active = profile.active_tiers()
    if not active:
        return {
            "evidence_strength_score": 0.0,
            "strongest_tier": None,
            "active_tiers": [],
            "version": EVIDENCE_STRENGTH_VERSION,
        }

    strongest = max(active, key=lambda t: TIER_WEIGHTS.get(t, 0.0))
    base = TIER_WEIGHTS.get(strongest, 0.0)

    bonus = 0.0
    for tier in active:
        if tier == strongest:
            continue
        bonus += _CORROBORATION_BONUS.get(tier, 0.0)
    if profile.testing_evidence:
        bonus += _CORROBORATION_BONUS["testing_evidence"]

    score = _clamp01(base + bonus)
    return {
        "evidence_strength_score": score,
        "strongest_tier": strongest,
        "active_tiers": active,
        "version": EVIDENCE_STRENGTH_VERSION,
    }


def detect_command_verb(text: str) -> Optional[str]:
    """Return the highest-depth command verb found in the criterion text."""
    if not text:
        return None
    lowered = text.lower()
    best: Optional[str] = None
    best_depth = -1
    for verb, depth in COMMAND_VERB_DEPTH.items():
        # word-ish boundary check without importing re for the hot path
        if verb in lowered and depth > best_depth:
            best = verb
            best_depth = depth
    return best


def required_strength_for_text(text: str) -> Dict[str, Any]:
    """Required evidence strength implied by the criterion's command verb."""
    verb = detect_command_verb(text)
    depth = COMMAND_VERB_DEPTH.get(verb or "", 2)
    return {
        "command_verb": verb,
        "command_verb_depth": depth,
        "required_strength": _DEPTH_REQUIRED_STRENGTH.get(depth, 0.45),
    }


def assess_criterion_evidence(
    *,
    criterion_text: str,
    profile: EvidenceProfile,
) -> Dict[str, Any]:
    """Full per-criterion verdict: strength score + required threshold + confidence.

    ``needs_deeper_verification`` is the routing signal: True means this criterion is
    a good candidate for the slow/expensive path (live runtime, ensemble, human flag).
    """
    strength = compute_evidence_strength_score(profile)
    score = float(strength["evidence_strength_score"])
    requirement = required_strength_for_text(criterion_text)
    required = float(requirement["required_strength"])

    margin = score - required
    if margin >= _HIGH_CONFIDENCE_MARGIN:
        decision_confidence = "high"
    elif margin <= -_LOW_CONFIDENCE_MARGIN:
        decision_confidence = "low"
    else:
        decision_confidence = "medium"

    return {
        "evidence_strength_score": score,
        "strongest_tier": strength["strongest_tier"],
        "active_tiers": strength["active_tiers"],
        "command_verb": requirement["command_verb"],
        "command_verb_depth": requirement["command_verb_depth"],
        "required_strength": required,
        "meets_required_strength": score >= required,
        "decision_confidence": decision_confidence,
        "needs_deeper_verification": decision_confidence != "high",
        "version": EVIDENCE_STRENGTH_VERSION,
    }


def profile_from_assets(
    assets: Dict[str, Any],
    *,
    runtime_observed: bool = False,
    gameplay_video_verified: bool = False,
    screenshots_only: bool = False,
    testing_evidence: Optional[bool] = None,
) -> EvidenceProfile:
    """Build an :class:`EvidenceProfile` from the evidence-gate ``assets`` dict."""
    return EvidenceProfile(
        source_present=bool(assets.get("has_source_code")),
        executable_present=bool(assets.get("has_executable")),
        gameplay_video_verified=gameplay_video_verified,
        runtime_observed=runtime_observed,
        screenshots_only=screenshots_only,
        testing_evidence=bool(
            assets.get("has_testing_doc") if testing_evidence is None else testing_evidence
        ),
    )
