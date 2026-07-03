"""Deterministic B.P3 / B.P4 design evidence assessment (PRO structural pass rules)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.pro_evidence_signals import (
    text_has_design_decisions,
    text_has_test_plan_evidence,
    text_has_user_testing_evidence,
)

RULE_BP3 = "design_evidence_rule_v1"
RULE_BP4 = "visual_design_rule_v1"
AUTH_BP3 = "DESIGN_EVIDENCE_RULE_V1"
AUTH_BP4 = "VISUAL_DESIGN_RULE_V1"

_GDD_DOC = re.compile(
    r"\b(gdd|game\s+design\s+document|design\s+document|وثيق(?:ة)?\s*تصميم|تصميم\s+اللعبة)\b",
    re.I,
)
_ART_ASSET = re.compile(
    r"\b(character|asset|sprite|شخصية|أصول|فنية|artistic|concept\s+art)\b",
    re.I,
)
_STRUCTURE = {
    "mechanics": re.compile(r"\b(mechanics?|mechanic|ميكانيك|gameplay\s+loop)\b", re.I),
    "levels": re.compile(r"\b(levels?|level\s+design|مستوى|مراحل)\b", re.I),
    "hud": re.compile(r"\b(hud|heads?-up|score\s+display|عرض\s+النقاط)\b", re.I),
    "controls": re.compile(r"\b(controls?|input|keyboard|wasd|تحكم|أزرار)\b", re.I),
    "game_flow": re.compile(r"\b(game\s+flow|flow|user\s+flow|تدفق|مسار\s+اللعب)\b", re.I),
}
_UI_VISUAL = re.compile(
    r"\b(ui|ux|interface|menu|screen|hud|wireframe|mockup|layout|"
    r"واجهة|شاشة|أزرار|تصميم\s+بصري|لقطة\s+شاشة)\b",
    re.I,
)
_SOURCE_SCENE = re.compile(r"\.(tscn|gd|gml|unity|cs)\b", re.I)


@dataclass
class DesignEvidenceBundle:
    corpus: str = ""
    design_doc_present: bool = False
    design_doc_gdd: bool = False
    structure_hits: List[str] = field(default_factory=list)
    ui_visual_count: int = 0
    embedded_image_count: int = 0
    survey_present: bool = False
    test_section_present: bool = False
    source_scenes_present: bool = False
    execution_mode: str = "PRO"

    @property
    def bp3_score(self) -> int:
        score = 0
        if self.design_doc_present and (self.design_doc_gdd or _ART_ASSET.search(self.corpus)):
            score += 1
        if len(self.structure_hits) >= 2:
            score += 1
        if self.ui_visual_count >= 1 or (
            self.embedded_image_count >= 3 and _UI_VISUAL.search(self.corpus)
        ):
            score += 1
        return score

    @property
    def bp4_score(self) -> int:
        score = 0
        if self.ui_visual_count >= 1 or _UI_VISUAL.search(self.corpus):
            score += 1
        if self.survey_present or self.test_section_present:
            score += 1
        return score


def _band_prefix(criteria_level: str) -> str:
    level = (criteria_level or "").strip().upper()
    if "." not in level:
        return ""
    return level.split(".")[0]


def is_b_band_criterion(criteria_level: str, short: str, expected: str) -> bool:
    level = (criteria_level or "").strip().upper()
    if level == f"B.{expected}" or level.endswith(f"/B.{expected}"):
        return True
    return _band_prefix(criteria_level) == "B" and short.upper() == expected


def build_design_evidence_bundle(
    *,
    corpus: str,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    execution_mode: str = "PRO",
) -> DesignEvidenceBundle:
    inv = artifact_inventory or {}
    text = corpus or ""

    docs = inv.get("documentation") or {}
    doc_files = docs.get("files") or []
    design_doc_present = (
        docs.get("status") in ("analyzed", "present", "partial")
        or bool(doc_files)
        or bool(re.search(r"\.(docx|pdf|doc)\b", text, re.I))
    )

    embedded = inv.get("embedded_screenshots") or {}
    embedded_count = int(
        embedded.get("count")
        or embedded.get("image_count")
        or len(embedded.get("images") or [])
        or 0
    )
    visual = inv.get("visual_verification") or inv.get("visual_evidence_summary") or {}
    ui_count = int(visual.get("screenshots_analyzed") or visual.get("image_count") or 0)
    if embedded_count:
        ui_count = max(ui_count, embedded_count)

    testing = inv.get("testing_evidence") or {}
    survey_present = (
        str(testing.get("status") or "").lower() in ("partial", "present", "complete", "detected")
        or text_has_user_testing_evidence(text)
    )
    test_section_present = text_has_test_plan_evidence(text) or text_has_design_decisions(text)

    paths_blob = "\n".join(
        str(p)
        for p in (
            inv.get("intake_relative_paths")
            or inv.get("submission_paths")
            or []
        )
    )
    source_paths = paths_blob + text
    source_scenes = bool(_SOURCE_SCENE.search(source_paths))

    structure_hits = [k for k, pat in _STRUCTURE.items() if pat.search(text)]

    return DesignEvidenceBundle(
        corpus=text,
        design_doc_present=design_doc_present,
        design_doc_gdd=bool(_GDD_DOC.search(text)),
        structure_hits=structure_hits,
        ui_visual_count=ui_count,
        embedded_image_count=embedded_count,
        survey_present=survey_present,
        test_section_present=test_section_present,
        source_scenes_present=source_scenes,
        execution_mode=execution_mode,
    )


def _evidence_found(bundle: DesignEvidenceBundle, keys: Sequence[str]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for key in keys:
        rows.append({"rule_key": key, "match": key, "snippet": key})
    return rows


def evaluate_bp3_deterministic(
    bundle: DesignEvidenceBundle,
    *,
    criteria_level: str,
    execution_mode: str,
) -> Tuple[bool, int, str, str, List[Dict[str, str]]]:
    score = bundle.bp3_score
    is_pro = execution_mode.upper() == "PRO"
    achieved = score >= 2
    verdict = "pass" if achieved else ("inconclusive" if not is_pro and score == 1 else "fail")
    if achieved:
        reason = f"bp3_signals={score}/3"
    elif verdict == "inconclusive":
        reason = "bp3_partial_corpus"
    else:
        reason = "bp3_design_evidence_insufficient"
    found = _evidence_found(
        bundle,
        [
            "design_doc" if bundle.design_doc_present else "",
            "structure" if len(bundle.structure_hits) >= 2 else "",
            "visual_artefact" if bundle.ui_visual_count >= 1 or bundle.embedded_image_count >= 3 else "",
        ],
    )
    found = [f for f in found if f["rule_key"]]
    det_score = 70 if achieved else (40 if verdict == "inconclusive" else 35)
    return achieved, det_score, reason, verdict, found


def evaluate_bp4_deterministic(
    bundle: DesignEvidenceBundle,
    *,
    criteria_level: str,
    execution_mode: str,
) -> Tuple[bool, int, str, str, List[Dict[str, str]]]:
    score = bundle.bp4_score
    is_pro = execution_mode.upper() == "PRO"
    # PRO: ≥1 visual-design OR survey/test signal (foundational pass, not peer review).
    achieved = score >= 1 if is_pro else score >= 2
    verdict = "pass" if achieved else ("inconclusive" if not is_pro and score == 1 else "fail")
    if achieved:
        reason = f"bp4_visual_signals={score}"
    elif verdict == "inconclusive":
        reason = "bp4_partial_corpus"
    else:
        reason = "bp4_visual_design_insufficient"
    found = _evidence_found(
        bundle,
        [
            "ui_visual" if bundle.ui_visual_count >= 1 or _UI_VISUAL.search(bundle.corpus) else "",
            "survey_or_test"
            if bundle.survey_present or bundle.test_section_present
            else "",
        ],
    )
    found = [f for f in found if f["rule_key"]]
    det_score = 70 if achieved else (40 if verdict == "inconclusive" else 35)
    return achieved, det_score, reason, verdict, found


def try_evaluate_design_criterion(
    *,
    criteria_level: str,
    corpus: str,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    execution_mode: str = "PRO",
) -> Optional[Dict[str, Any]]:
    """Return deterministic row dict for B.P3/B.P4, or None if not applicable."""
    from app.rubric.deterministic_engine import _normalize_level, _wrap_row

    short = _normalize_level(criteria_level)
    if not is_b_band_criterion(criteria_level, short, "P3") and not is_b_band_criterion(
        criteria_level, short, "P4"
    ):
        return None

    bundle = build_design_evidence_bundle(
        corpus=corpus,
        artifact_inventory=artifact_inventory,
        execution_mode=execution_mode,
    )

    if is_b_band_criterion(criteria_level, short, "P3"):
        achieved, det_score, reason, verdict, found = evaluate_bp3_deterministic(
            bundle, criteria_level=criteria_level, execution_mode=execution_mode
        )
        return _wrap_row(
            criteria_level=criteria_level,
            rule_id=RULE_BP3,
            execution_mode=execution_mode,
            runtime="design_evidence",
            achieved=achieved,
            score=det_score,
            reason=reason,
            authority=AUTH_BP3,
            verdict_status=verdict,
            text=bundle.corpus,
            evidence_rules=tuple((k, _GDD_DOC) for k in ("gdd", "design")),
            extra_found=found,
        )

    achieved, det_score, reason, verdict, found = evaluate_bp4_deterministic(
        bundle, criteria_level=criteria_level, execution_mode=execution_mode
    )
    return _wrap_row(
        criteria_level=criteria_level,
        rule_id=RULE_BP4,
        execution_mode=execution_mode,
        runtime="visual_design",
        achieved=achieved,
        score=det_score,
        reason=reason,
        authority=AUTH_BP4,
        verdict_status=verdict,
        text=bundle.corpus,
        evidence_rules=(("ui_visual", _UI_VISUAL),),
        extra_found=found,
    )
