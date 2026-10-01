"""
Runtime Evidence Gate — Pearson-grade single authority for runtime-dependent criteria.

Golden rule (PRO governance):
    A runtime-dependent criterion (C.P5 / C.P6 / C.M3) may NOT be awarded
    unless the game was *actually* shown to run / be played. Documents, slides,
    images, AI description, static analysis (incl. Scratch static graph), and the
    mere *presence* of a project/.sb3/.exe are NOT sufficient on their own.

Evidence PATHS vs criterion AWARDABILITY (three distinct things — do not conflate):

    a. Evidence *paths* (``evaluate_runtime_evidence`` → ``satisfied``). Any ONE of
       these means "some runtime-related evidence exists", which only lifts the
       blanket "runtime not verified" block:
         1. Runtime PASS         — real launch + gameplay validation (engine sandbox)
         2. Gameplay video       — documented gameplay footage (detected/documented)
         3. L5 playtest         — visually-corroborated playtest record (an evidence path)
         4. Playtest review recorded
    b. Runtime gameplay *validated* — the engine sandbox actually launched and played
       the build.  A gameplay video is NOT this: it is documented evidence only.
    c. Criterion *awardability* (``BTECCriterionMapper.evaluate`` → ``criterion_pass``).
       C.P5 / C.P6 / C.M3 additionally need the per-criterion automated L4 verdict
       (and C.P6 test documentation; C.M3 also P5+P6 and a provable V1→V2 code diff).
       The whole gate is fully automated — no criterion waits on a human decision;
       missing evidence simply means NOT_VERIFIED.
       A video-only or L5-only submission therefore satisfies (a) but is NOT awardable
       under (c).

If a submission is a game project but NONE of the above is present, every gated
criterion is forced to achieved=False / awardable=False and marked with a
non-bypassable ``runtime_gate_block`` flag so no later promotion path can re-award
it. The final BTEC band is then recomputed (a missing mandatory Pass criterion ⇒ U).

This module is the terminal "seal": it is invoked LAST in
``finalize_grading_criteria_results`` (which runs on grade, on DB persist, and on
every results/Word/PDF read path), so the same blocked decision is reflected in the
UI, the Word report, the PDF report, the API and the dashboard.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from app.btec_criteria_governance import _demote_row, _short_level
from app.btec_grade_resolution import determine_grade_level
from app.game_engine_signatures import (
    detect_engine_from_text,
    has_runnable_game_project,
)

GATE_VERSION = "runtime_evidence_gate_v1"
BTEC_MAPPER_VERSION = "btec_criterion_mapper_v1"

_L4_RANK = {"L3": 0, "L4_partial": 1, "L4_full": 2}

# Binary gameplay requirements that can be proved either by a direct playtest
# or by the verifier's source+runtime corroboration.  Documentation-only
# requirements (for example level design) are assessed by their own rubric and
# must not make the runtime gate impossible to satisfy.
_RUNTIME_CRITICAL_REQUIREMENTS = frozenset(
    {
        "player_movement",
        "jump",
        "collect_items",
        "score_system",
        "enemy_interaction",
        "win_condition",
        "lose_condition",
        "restart",
        "menu_ui",
    }
)


def _required_feature_verification(verification: Dict[str, Any]) -> Dict[str, Any]:
    """Summarise required feature proof for the criterion gate.

    Runtime rows already encode the evidence authority: direct playtest rows
    use ``runtime_l4/runtime_l5`` while complete source implementation that is
    corroborated by a real run uses ``cross_modal_l4``.  A source mention or a
    confidence percentage by itself is deliberately not accepted.

    Older snapshots may not contain the checklist/package.  In that case the
    legacy aggregate gate remains available rather than silently changing old
    results during read-time migration.
    """
    checklist = verification.get("requirement_checklist") or {}
    package = verification.get("runtime_evidence_package") or {}
    checklist_rows = checklist.get("requirements") or []
    confidence_rows = package.get("requirement_confidence") or []
    if not isinstance(checklist_rows, list) or not isinstance(confidence_rows, list):
        return {"available": False, "required": [], "verified": [], "missing": []}

    required = []
    for row in checklist_rows:
        if not isinstance(row, dict):
            continue
        req_id = str(row.get("id") or "").strip()
        applicability = str(row.get("applicability") or "not_mentioned")
        if req_id in _RUNTIME_CRITICAL_REQUIREMENTS and applicability == "required":
            required.append(req_id)

    by_id = {
        str(row.get("requirement") or "").strip(): row
        for row in confidence_rows
        if isinstance(row, dict) and row.get("requirement")
    }
    if not required or not all(req_id in by_id for req_id in required):
        return {"available": False, "required": required, "verified": [], "missing": required}

    verified: List[str] = []
    missing: List[str] = []
    proof: Dict[str, str] = {}
    for req_id in required:
        row = by_id[req_id]
        source = str(row.get("confidence_source") or "")
        # ``verified`` is authoritative.  It may originate from direct runtime
        # or source+runtime reconciliation, never from documentation alone.
        if row.get("verified") is True and source in {
            "runtime_l4",
            "runtime_l5",
            "cross_modal_l4",
        }:
            verified.append(req_id)
            proof[req_id] = source
        else:
            missing.append(req_id)

    return {
        "available": True,
        "required": required,
        "verified": verified,
        "missing": missing,
        "proof": proof,
        "all_verified": not missing,
    }


@dataclass(frozen=True)
class GateRule:
    """Per-criterion gate policy (Option C — spec §1.2)."""

    criterion: str
    automatic: bool
    min_l4_level: str = "L4_partial"
    min_test_doc_entries: int = 0


# Fully automated policy — no human confirmation anywhere.  Every criterion opens
# only from verifiable automated evidence; missing evidence means NOT_VERIFIED.
#   P5  L4_partial runtime + required gameplay features
#   P6  L4_partial runtime + test documentation + required gameplay features
#   M3  L4_full runtime + test documentation + required features + P5 & P6 passed
#       + a provable V1→V2 code diff (see app/version_code_diff.py)
#   D3  M3 passed + L4_full runtime (the documentary standard is judged by the
#       academic layer; the gate only enforces the dependency and the runtime floor)
DEFAULT_GATE_RULES: tuple[GateRule, ...] = (
    GateRule("P5", automatic=True, min_l4_level="L4_partial"),
    GateRule("P6", automatic=True, min_l4_level="L4_partial", min_test_doc_entries=2),
    GateRule("M3", automatic=True, min_l4_level="L4_full", min_test_doc_entries=1),
    GateRule("D3", automatic=True, min_l4_level="L4_full"),
)


def get_cp6_min_test_entries(grading_mode: str | None = None) -> int:
    """PRO: ≥1 test doc entry opens C.P6; STANDARD keeps ≥2."""
    from app.grading_mode import GradingMode

    if GradingMode.from_wire(grading_mode) is GradingMode.STANDARD:
        return 2
    return 1


def build_gate_rules(grading_mode: str | None = None) -> tuple[GateRule, ...]:
    """Build gate rules; C.P6 test-doc threshold varies by grading mode."""
    cp6_min = get_cp6_min_test_entries(grading_mode)
    rules: list[GateRule] = []
    for rule in DEFAULT_GATE_RULES:
        if rule.criterion == "P6" and rule.min_test_doc_entries != cp6_min:
            rules.append(
                GateRule(
                    rule.criterion,
                    automatic=rule.automatic,
                    min_l4_level=rule.min_l4_level,
                    min_test_doc_entries=cp6_min,
                )
            )
        else:
            rules.append(rule)
    return tuple(rules)


@dataclass
class GateDecision:
    criterion: str
    open: bool
    automatic: bool
    reason: str = ""
    reason_ar: str = ""
    evidence_chain: List[str] = field(default_factory=list)
    ai_academic_verified: bool = False
    ai_verification_confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "criterion": self.criterion,
            "open": self.open,
            "automatic": self.automatic,
            "reason": self.reason,
            "reason_ar": self.reason_ar,
            "evidence_chain": list(self.evidence_chain),
            "ai_academic_verified": self.ai_academic_verified,
            "ai_verification_confidence": self.ai_verification_confidence,
        }


_HIGHER_BAND_AI_MARKERS: Dict[str, tuple[str, ...]] = {
    "M3": (
        "فعال",
        "منظم",
        "تقني",
        "تحسين",
        "ملاحظ",
        "اختبار",
        "اعتبارات",
        "effective",
        "technical",
    ),
    "D3": (
        "مقنع",
        "شامل",
        "نقد",
        "استراتيج",
        "تبرير",
        "بيانات",
        "نسب",
        "persuasive",
        "critical",
        "strategic",
    ),
}


def _assess_ai_academic_evidence(
    row: Optional[Dict[str, Any]], criterion: str, *, student_text: str = ""
) -> Dict[str, Any]:
    """Advisory academic-evidence check for higher bands (never opens a gate).

    Runtime proves that the prototype works.  This check independently requires
    the stored AI/deterministic rubric verdict plus traceable documentary evidence
    and criterion-specific language before Merit/Distinction can be opened.
    """
    cr = row if isinstance(row, dict) else {}
    deterministic = cr.get("deterministic_rubric") or {}
    deterministic_pass = bool(deterministic.get("deterministic_achieved")) and str(
        deterministic.get("verdict_status") or "pass"
    ).lower() == "pass"

    matrix = [item for item in (cr.get("decision_matrix") or []) if isinstance(item, dict)]
    matrix_evidence = any(str(item.get("evidence") or "").strip() for item in matrix)
    matrix_reasoning = any(str(item.get("reasoning") or "").strip() for item in matrix)
    covered_points = any(str(item or "").strip() for item in (cr.get("covered_points") or []))
    missing_clear = not any(str(item or "").strip() for item in (cr.get("missing_points") or []))

    authority = (
        ((deterministic.get("evidence_registry") or {}).get("visual_evidence") or {}).get(
            "authority"
        )
        or {}
    )
    authority_sufficient = authority.get("authority_sufficient") is not False
    academic_text = "\n".join(
        [
            str(cr.get("feedback") or ""),
            *(str(item.get("evidence") or "") for item in matrix),
            *(str(item.get("reasoning") or "") for item in matrix),
            *(str(item or "") for item in (cr.get("covered_points") or [])),
        ]
    ).lower()
    marker_hits = sorted(
        {marker for marker in _HIGHER_BAND_AI_MARKERS.get(criterion, ()) if marker in academic_text}
    )
    semantic_match = len(marker_hits) >= 2

    # BC.D3 is documentary rather than a mechanic by itself.  A specialised
    # deterministic rule may verify the complete planning/responsibility trail
    # from Aim B + Aim C even when the initial AI narrative incorrectly asks for
    # a human/project-log review.  Runtime still has to pass separately below.
    documentary_verified = False
    if (
        criterion == "D3"
        and deterministic.get("rule_id") == "bc_d3_self_management"
        and deterministic_pass
    ):
        from app.pro_evidence_signals import text_has_d3_self_management_evidence

        documentary_verified = text_has_d3_self_management_evidence(student_text)

    if documentary_verified:
        return {
            "verified": True,
            "confidence": 1.0,
            "checks": {
                "deterministic_pass": True,
                "documentary_self_management": True,
                "complete_student_corpus": True,
            },
            "marker_hits": marker_hits,
        }

    checks = {
        "deterministic_pass": deterministic_pass,
        "matrix_evidence": matrix_evidence,
        "matrix_reasoning": matrix_reasoning,
        "covered_points": covered_points,
        "missing_points_clear": missing_clear,
        "authority_sufficient": authority_sufficient,
        "criterion_semantics": semantic_match,
    }
    weights = {
        "deterministic_pass": 0.30,
        "matrix_evidence": 0.20,
        "matrix_reasoning": 0.15,
        "covered_points": 0.10,
        "missing_points_clear": 0.10,
        "authority_sufficient": 0.05,
        "criterion_semantics": 0.10,
    }
    confidence = round(sum(weights[key] for key, passed in checks.items() if passed), 2)
    return {
        "verified": all(checks.values()),
        "confidence": confidence,
        "checks": checks,
        "marker_hits": marker_hits,
    }


_CODE_DIFF_REASON_AR = {
    "not_evaluated": "لم يُقيَّم فرق الكود بين V1 وV2 — لا يُفتح C.M3 بلا دليل تحسين في الكود.",
    "versions_not_found": "لم يُعثر على نسختين مميّزتين V1 وV2 — لا يمكن إثبات التحسين بالكود.",
    "versions_not_separable": "تعذّر فصل V1 عن V2 بوضوح في ملفات الطالب — لا يمكن إثبات التحسين.",
    "no_submission_root": "تعذّر تحديد مجلد ملفات الطالب لمقارنة النسخ.",
    "no_code_change": "لا يوجد أي تغيير فعلي في الكود/الموارد بين V1 وV2 — لا تحسين قابل للإثبات.",
    "no_claims_to_link": "يوجد فرق بين النسختين لكن لم تُرصد تحسينات معلنة يمكن ربطها به.",
    "improvements_mostly_unsupported": (
        "أغلب التحسينات المعلنة لا أثر لها في الكود بين V1 وV2 (Unsupported) — لا يُفتح C.M3."
    ),
    "error": "تعذّر إجراء مقارنة الكود بين V1 وV2 — لا يُفتح C.M3.",
}


def _code_diff_gate_view(code_diff: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalise the V1→V2 code-diff report into the M3 gate's ok/reason/chain."""
    if not isinstance(code_diff, dict) or not code_diff.get("evaluated"):
        status = "not_evaluated"
        return {
            "ok": False,
            "reason": "m3_code_diff_not_evaluated",
            "reason_ar": _CODE_DIFF_REASON_AR[status],
            "chain": ["m3_code_diff=not_evaluated"],
        }
    status = str(code_diff.get("status") or "error")
    ok = bool(code_diff.get("ok"))
    chain = [
        f"m3_code_diff={status}",
        f"m3_code_diff_changes={int(code_diff.get('substantive_change_count') or 0)}",
        f"m3_claims_supported={int(code_diff.get('supported_claims') or 0)}"
        f"/{int(code_diff.get('claims_total') or 0)}",
    ]
    return {
        "ok": ok,
        "reason": "m3_code_diff_supported" if ok else f"m3_code_diff_{status}",
        "reason_ar": (
            "التحسين مثبت بفرق الكود بين V1 وV2"
            if ok
            else _CODE_DIFF_REASON_AR.get(status, _CODE_DIFF_REASON_AR["error"])
        ),
        "chain": chain,
    }


class BTECCriterionMapper:
    """Map EvidencePackage / gameplay verification to per-criterion gate decisions."""

    def __init__(
        self,
        rules: Sequence[GateRule] | None = None,
        *,
        grading_mode: str | None = None,
    ) -> None:
        self.rules = tuple(rules or build_gate_rules(grading_mode))

    def _l4_satisfies(self, l4_level: str, min_level: str) -> bool:
        return _L4_RANK.get(l4_level, 0) >= _L4_RANK.get(min_level, 0)

    def evaluate(
        self,
        verification: Optional[Dict[str, Any]],
        *,
        test_doc_entries: int = 0,
        functional_smoke_pass: bool = False,
        criteria_results: Optional[Sequence[Dict[str, Any]]] = None,
        engine_id: Optional[str] = None,
        student_text: str = "",
        code_diff: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from app.gameplay_verifier import calculate_l4_level

        gv = verification or {}
        gameplay_entered = bool(gv.get("gameplay_entered"))
        mechanics = int(gv.get("mechanics_verified_count") or 0)
        l4 = str(
            gv.get("l4_level")
            or gv.get("automated_l4_level")
            or calculate_l4_level(
                gameplay_entered=gameplay_entered,
                mechanics_verified_count=mechanics,
            )
        )
        movement = bool(gv.get("player_movement_verified"))
        shots = int(gv.get("gameplay_window_screenshots") or 0)
        evidence_pkg = gv.get("evidence_package") or {}
        req_results = evidence_pkg.get("results") or []
        required_features = _required_feature_verification(gv)
        required_features_ok = (
            bool(required_features.get("all_verified"))
            if required_features.get("available")
            else True
        )
        engine = str(engine_id or gv.get("engine_id") or "").strip().lower()
        criteria_by_short = {
            _short_level(str(row.get("criteria_level") or "")): row
            for row in (criteria_results or [])
            if isinstance(row, dict)
        }

        decisions: List[GateDecision] = []
        criterion_pass: Dict[str, bool] = {}

        for rule in self.rules:
            chain: List[str] = [
                f"l4_level={l4}",
                f"gameplay_entered={gameplay_entered}",
                f"mechanics_verified={mechanics}",
                f"test_doc_entries={test_doc_entries}",
            ]
            for row in req_results:
                if isinstance(row, dict) and row.get("verified"):
                    chain.append(f"req:{row.get('req_id')}=verified")
            if required_features.get("available"):
                chain.append(
                    "required_features="
                    + ("verified" if required_features_ok else "missing")
                )
                for req_id in required_features.get("verified") or []:
                    proof = (required_features.get("proof") or {}).get(req_id) or "verified"
                    chain.append(f"required:{req_id}={proof}")
                for req_id in required_features.get("missing") or []:
                    chain.append(f"required:{req_id}=unverified")

            l4_ok = self._l4_satisfies(l4, rule.min_l4_level)
            test_ok = test_doc_entries >= rule.min_test_doc_entries
            runtime_ok = functional_smoke_pass or gameplay_entered or movement
            # Advisory only: shown in the report, never opens a gate by itself.
            academic = (
                _assess_ai_academic_evidence(
                    criteria_by_short.get(rule.criterion),
                    rule.criterion,
                    student_text=student_text,
                )
                if rule.criterion in {"M3", "D3"}
                else {"verified": False, "confidence": 0.0, "checks": {}, "marker_hits": []}
            )

            open_gate = l4_ok and runtime_ok and test_ok
            reason = "automatic_l4" if open_gate else "evidence_insufficient"
            reason_ar = (
                f"بوابة تلقائية — L4 {l4}" if open_gate else "أدلة L4 غير كافية لفتح البوابة"
            )
            if rule.criterion == "P5":
                open_gate = open_gate and (movement or mechanics >= 1) and required_features_ok
            elif rule.criterion in {"P6", "M3"}:
                open_gate = open_gate and required_features_ok

            if rule.criterion == "M3":
                m3_diff = _code_diff_gate_view(code_diff)
                chain.extend(m3_diff["chain"])
                prerequisite_ok = bool(criterion_pass.get("P5") and criterion_pass.get("P6"))
                chain.append(f"prerequisite_p5_p6={prerequisite_ok}")
                open_gate = open_gate and prerequisite_ok and m3_diff["ok"]
            elif rule.criterion == "D3":
                m3_ok = bool(criterion_pass.get("M3"))
                chain.append(f"prerequisite_m3={m3_ok}")
                open_gate = open_gate and m3_ok

            if not open_gate:
                # Every closed gate is NOT_VERIFIED with its first concrete missing piece.
                if not l4_ok or not runtime_ok:
                    reason = "evidence_insufficient"
                    reason_ar = "أدلة L4 غير كافية لفتح البوابة"
                elif rule.min_test_doc_entries and not test_ok:
                    reason = "test_documentation_insufficient"
                    reason_ar = (
                        f"يتطلب ≥{rule.min_test_doc_entries} مدخلات وثائق اختبار "
                        f"(موجود: {test_doc_entries})"
                    )
                elif rule.criterion in {"P5", "P6", "M3"} and not required_features_ok:
                    missing_labels = ", ".join(required_features.get("missing") or [])
                    reason = "required_gameplay_features_unverified"
                    reason_ar = (
                        "لم تثبت كل ميزات اللعبة المطلوبة بالتشغيل أو بتحقق الكود "
                        f"المقترن بالتشغيل: {missing_labels}"
                    )
                elif rule.criterion == "M3" and not prerequisite_ok:
                    reason = "prerequisite_p5_p6_not_met"
                    reason_ar = "لم يتحقق C.P5/C.P6 آلياً، لذلك لا يُفتح C.M3"
                elif rule.criterion == "M3":
                    reason = m3_diff["reason"]
                    reason_ar = m3_diff["reason_ar"]
                elif rule.criterion == "D3":
                    reason = "prerequisite_m3_not_met"
                    reason_ar = "لم يتحقق C.M3 (تحسين مثبت بالكود والتشغيل)، لذلك لا يُفتح C.D3"

            if shots >= 1:
                chain.append(f"gameplay_window_screenshots={shots}")

            decision = GateDecision(
                criterion=rule.criterion,
                open=open_gate,
                automatic=rule.automatic,
                reason=reason,
                reason_ar=reason_ar,
                evidence_chain=chain,
                ai_academic_verified=bool(academic.get("verified")),
                ai_verification_confidence=float(academic.get("confidence") or 0.0),
            )
            decisions.append(decision)
            criterion_pass[rule.criterion] = open_gate

        l4_full = l4 == "L4_full"
        l4_partial = l4 in ("L4_full", "L4_partial")

        return {
            "version": BTEC_MAPPER_VERSION,
            "l4_level": l4,
            "l4_full": l4_full,
            "l4_partial": l4_partial and not l4_full,
            "criterion_pass": criterion_pass,
            "decisions": [d.to_dict() for d in decisions],
            "engine_id": engine or None,
            "higher_band_verification": "policy_default",
            "required_feature_verification": required_features,
            "summary_ar": (
                f"L4 آلي ({l4}) — ميكانيكا={mechanics} لقطات={shots}"
                if l4_partial or l4_full
                else "L3 — إطلاق بدون gameplay مؤكد"
            ),
        }


# Runtime-dependent criteria: prototype production, testing, and refinement.
# BC.D3 assesses responsibility/creativity/self-management, not a mechanic.
RUNTIME_GATED_SHORT = frozenset({"P5", "P6", "M3"})

_RUNTIME_GATE_AUTHORITY = "RUNTIME_GATE_BLOCKED"

_GATE_REASON_AR = (
    "بوابة التحقق من التشغيل (Runtime Gate): لم يُثبَت تشغيل/لعب اللعبة فعلياً. "
    "لا يُمنح هذا المعيار بالاعتماد على التقرير أو العرض التقديمي أو الصور أو "
    "التحليل الساكن أو مجرد وجود ملفات المشروع (.sb3/.exe). الأدلة المقبولة: "
    "تشغيل ناجح موثّق (Runtime PASS)، أو فيديو لعب (Gameplay Video)، أو مراجعة "
    "بشرية (L5 Playtest)."
)

# Appended when the automated run failed because the grading platform could not
# capture the game window (environment fault) — never the student's fault.
_GATE_CAPTURE_ENV_NOTE_AR = (
    " ملاحظة: فشل التحقق الآلي في هذه الجلسة سببه تعذّر التقاط نافذة اللعبة على "
    "منصة التصحيح (عطل بيئة التقاط — لا يدل على خلل في لعبة الطالب). يُنصح "
    "بإعادة التشغيل الآلي بعد تهيئة بيئة الالتقاط، أو اعتماد فيديو لعب/مراجعة "
    "بشرية (L5)."
)

_CAPTURE_ENV_FAILURE_CODES = frozenset({"GAME_WINDOW_CAPTURE_FAILED", "WINDOW_NOT_FOUND"})


def _gate_reason_for(gv: Dict[str, Any]) -> str:
    """Gate reason wording; distinguishes platform capture faults from game faults."""
    code = str((gv or {}).get("failure_reason_code") or "")
    status = str(((gv or {}).get("menu_navigation") or {}).get("status") or "").lower()
    if code in _CAPTURE_ENV_FAILURE_CODES or (
        "capture" in status and ("fail" in status or "preflight" in status)
    ):
        return _GATE_REASON_AR + _GATE_CAPTURE_ENV_NOTE_AR
    return _GATE_REASON_AR

# Teacher-facing copy — L4 automated run ≠ in-game gameplay evidence (Unit 9 calibration).
RUNTIME_L4_TEACHER_NOTE_AR = (
    "التشغيل الآلي على الخادم وفحص الملفات لا يُعتبر دليلاً كاملاً على اللعب الفعلي "
    "(Gameplay). لتحقيق C.P5/C.P6/C.M3 يجب تقديم أدلة تشغيل واضحة من داخل "
    "اللعبة: فيديو لعب يظهر حركة اللاعب ونظام النقاط وتفاعل العدو، أو اختبار بشري "
    "موثّق (L5 Playtest)."
)

RUNTIME_SCREENSHOTS_CAPTION_AR = (
    "لقطات التشغيل (مرصودة — لا تثبت gameplay): هذه اللقطات من جلسة التشغيل الآلي "
    "على منصة التصحيح، وليست من داخل اللعبة نفسها."
)


def _promote_l4_gate_row(
    row: Dict[str, Any], *, decision: Optional[Dict[str, Any]] = None
) -> None:
    """Align achieved/score when automated runtime/AI evidence certifies a row."""
    short = _short_level(str(row.get("criteria_level") or ""))
    minimum_score = {"M3": 85, "D3": 95}.get(short, 75)
    det = row.get("deterministic_rubric") or {}
    if not row.get("achieved"):
        row["achieved"] = True
        row["score"] = max(int(row.get("score") or 0), minimum_score)
        row["verdict_status"] = "pass"
        auth = str(det.get("authority") or row.get("achievement_authority") or "")
        blocked_authorities = {
            _RUNTIME_GATE_AUTHORITY,
            "HUMAN_REVIEW_REQUIRED",
            "RUNTIME_INSUFFICIENT",
            "NONE",
            "",
        }
        if auth and auth not in blocked_authorities:
            row["achievement_authority"] = auth
        else:
            row["achievement_authority"] = "RUNTIME_L4_GATE"
    if (
        short in RUNTIME_GATED_SHORT
        and isinstance(det, dict)
        and det
        and (
            det.get("deterministic_achieved") is not True
            or str(det.get("reason") or "") == "no_code_evidence"
            or str((det.get("evidence_registry") or {}).get("result") or "").lower()
            == "fail"
        )
    ):
        # Preserve the pre-runtime rule for audit, but never leave a failed
        # nested verdict beside a terminal L4 pass at the same criterion.
        row.setdefault("pre_runtime_deterministic_rubric", copy.deepcopy(det))
        aligned = copy.deepcopy(det)
        aligned.update(
            {
                "deterministic_achieved": True,
                "deterministic_score": max(
                    int(aligned.get("deterministic_score") or 0), minimum_score
                ),
                "verdict_status": "pass",
                "reason": "runtime_l4_verified_override",
                "authority": "RUNTIME_VALIDATION",
            }
        )
        registry = aligned.get("evidence_registry")
        if isinstance(registry, dict):
            registry.update(
                {
                    "result": "pass",
                    "reason": "runtime_l4_verified_override",
                    "runtime": "L4_verified",
                    "authority": "RUNTIME_VALIDATION",
                }
            )
        row["deterministic_rubric"] = aligned
        if short in {"P5", "P6"}:
            row["achievement_authority"] = "RUNTIME_VALIDATION"
    if short in {"M3", "D3"}:
        # Higher bands open only from verifiable automated evidence (L4_full runtime,
        # P5+P6, test documentation and — for M3 — a provable V1→V2 code diff).
        # Never an AI/regex composite and never waiting on a human decision.
        row["achievement_authority"] = "AUTOMATED_RUNTIME_GATE"
        row["ai_verification"] = {
            "status": "advisory_only",
            "automatic": True,
            "human_review_required": False,
            "confidence": float((decision or {}).get("ai_verification_confidence") or 0.0),
            "method": "l4_full_runtime_plus_code_diff",
        }
        academic_snapshot = row.get("academic_snapshot")
        if isinstance(academic_snapshot, dict):
            academic_snapshot["human_review_required"] = {
                "required": False,
                "severity": "none",
                "reasons": ["resolved_by_automated_runtime_gate"],
            }
    # Engine governance runs before the terminal runtime seal.  Once the
    # criterion's L4 + document requirements pass, its earlier temporary hold
    # is stale and must not leak into the report beside an Achieved verdict.
    row.pop("pro_gameplay_governance_hold", None)
    row.pop("engine_governance_engine", None)
    row.pop("governance_adjustment_ar", None)
    row.pop("award_block_reason", None)
    row.pop("award_block_reason_ar", None)
    if short == "P6":
        row["feedback"] = (
            "تحقق المعيار بعد تشغيل اللعبة فعلياً داخل GameMaker بمستوى L4، "
            "ومطابقة نتائج اللعب مع توثيق الاختبار المرفق."
        )
    elif short == "M3":
        row["feedback"] = (
            "تحقق C.M3 آلياً: أُثبت تشغيل اللعبة بمستوى L4_full مع تحقق C.P5/C.P6 "
            "وسجل اختبار، وتحسين موثّق قابل للإثبات بفرق الكود بين V1 وV2."
        )
    elif short == "D3":
        row["feedback"] = (
            "تحقق شرط C.D3 آلياً: تحقق C.M3 وثبت التشغيل بمستوى L4_full."
        )
    else:
        row["feedback"] = (
            "تحقق المعيار بعد تشغيل اللعبة فعلياً داخل GameMaker بمستوى L4 "
            "وإثبات الدخول إلى حلقة اللعب وتجربة الميكانيكا داخل نافذة اللعبة."
        )
    row["runtime_observation_note_ar"] = (
        "تحقق آلي مباشر: تم فتح اللعبة والدخول إلى gameplay وتنفيذ اختبارات "
        "الميكانيكا داخل نافذة اللعبة، وربط النتائج بالأدلة الأكاديمية آلياً."
    )
    row["runtime_l4_verified"] = True
    row["report_display_status"] = "achieved"
    row["missing_points"] = []
    matrix = row.get("decision_matrix")
    if isinstance(matrix, list):
        for item in matrix:
            if isinstance(item, dict):
                item["met"] = True


def _align_overall_feedback_after_runtime_open(grading_result: Dict[str, Any]) -> None:
    """Replace stale pre-gate praise/hold text with the terminal decision."""
    rows = [r for r in (grading_result.get("criteria_results") or []) if isinstance(r, dict)]
    achieved = [str(r.get("criteria_level") or "") for r in rows if r.get("achieved")]
    pending = [str(r.get("criteria_level") or "") for r in rows if not r.get("achieved")]
    grade = str(grading_result.get("grade_level") or "U")
    grading_result["overall_feedback"] = (
        f"التقدير النهائي المعتمد: {grade}. "
        f"تحققت المعايير: {', '.join(achieved) or '-'}. "
        "تم اعتماد C.P5 وC.P6 بعد تشغيل اللعبة فعلياً والتحقق من gameplay "
        "والميكانيكا ووثائق الاختبار. "
        f"المعايير التي لم تتحقق بعد: {', '.join(pending) or '-'}؛ "
        "وتحتاج أدلة آلية أو وثائق إضافية بحسب متطلبات كل معيار."
    )


def _collect_paths(
    grading_result: Optional[Dict[str, Any]],
    inventory: Optional[Dict[str, Any]],
) -> List[str]:
    pool: List[str] = []
    for src_obj in (grading_result or {}, inventory or {}):
        for key in ("submission_paths", "intake_relative_paths"):
            val = src_obj.get(key)
            if isinstance(val, list):
                pool.extend(str(p) for p in val if p)
    return pool


def _compute_m3_code_diff(
    grading_result: Dict[str, Any],
    criteria: Sequence[Dict[str, Any]],
    submission_paths: Sequence[str],
) -> Optional[Dict[str, Any]]:
    """V1→V2 code-diff evidence, computed only when a C.M3 row exists.

    Any failure is reported as an error status (M3 stays blocked) — never skipped.
    """
    has_m3 = any(
        isinstance(r, dict) and _short_level(str(r.get("criteria_level") or "")) == "M3"
        for r in criteria
    )
    if not has_m3:
        return None
    previous = grading_result.get("m3_code_diff")
    try:
        from app.version_code_diff import evaluate_m3_code_diff

        diff = evaluate_m3_code_diff(
            submission_paths, str(grading_result.get("student_text") or "")
        )
        # Files gone for good (cleaned up after grading): keep the verdict that was
        # already computed from them.  Any *present* evidence is always re-read, so
        # new or changed files (a later V2, RESUME) are never answered from a stale copy.
        if (
            diff.get("status") == "no_submission_root"
            and isinstance(previous, dict)
            and previous.get("evaluated")
            and previous.get("status") != "no_submission_root"
        ):
            diff = previous
    except Exception as err:  # pragma: no cover - defensive
        diff = {"evaluated": True, "ok": False, "status": "error", "error": str(err)}
    grading_result["m3_code_diff"] = diff
    return diff


def _code_diff_summary(code_diff: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(code_diff, dict):
        return None
    keep = (
        "version", "evaluated", "ok", "status", "v1_root", "v2_root",
        "substantive_change_count", "claims_total", "supported_claims",
        "supported_ratio", "unsupported_claims",
    )
    return {k: code_diff.get(k) for k in keep if k in code_diff}


_GATE_ERROR_AUTHORITY = "RUNTIME_GATE_ERROR"
_FAIL_CLOSED_SHORT = RUNTIME_GATED_SHORT | {"D3"}
_GATE_ERROR_REASON_AR = (
    "تعذّر تنفيذ بوابة التحقق من التشغيل بسبب خطأ داخلي، لذلك لا يُمنح هذا المعيار "
    "(NOT VERIFIED): التحقق الآلي غير مكتمل، ويُعاد تقييمه تلقائياً عند نجاح البوابة."
)
_PRE_GATE_KEYS = ("achieved", "score", "verdict_status")


def _row_state(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: row.get(k) for k in _PRE_GATE_KEYS}


def _clear_runtime_gate_error(grading_result: Dict[str, Any]) -> None:
    """The gate ran again and succeeded: drop a stale error marker and its NOT_VERIFIED flags."""
    err = grading_result.pop("runtime_gate_error", None)
    if not isinstance(err, dict):
        return
    prior = err.get("prior") or {}
    if grading_result.get("grade_decision_status") == "NOT_VERIFIED":
        for key in ("grade_decision_status", "official_grade_provisional",
                    "evidence_required", "grade_level_provisional"):
            if prior.get(key) is None:
                grading_result.pop(key, None)
            else:
                grading_result[key] = prior[key]


def _looks_like_game_fail_safe(
    grading_result: Dict[str, Any], artifact_inventory: Optional[Dict[str, Any]]
) -> bool:
    """Game detection for the error path: if detection itself fails, assume a game (fail closed)."""
    try:
        inv = artifact_inventory or grading_result.get("artifact_inventory") or {}
        return is_game_submission(inv, submission_paths=_collect_paths(grading_result, inv))
    except Exception:
        return True


def apply_runtime_gate_fail_closed(
    grading_result: Dict[str, Any],
    error: BaseException,
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """The terminal seal itself failed → nothing runtime-dependent may stay awarded.

    Called by the finalizer instead of swallowing the exception.  It never raises:
    P5/P6/M3/D3 are demoted (they cannot be trusted from an earlier layer),
    ``runtime_gate_error`` records why, the decision becomes NOT_VERIFIED /
    provisional ("automated verification incomplete — evidence required"; no human
    review is requested), and the grade is recomputed from the demoted rows.  A later
    successful gate run clears the marker and re-evaluates normally.
    """
    err: Dict[str, Any] = {
        "version": GATE_VERSION,
        "status": "NOT_VERIFIED",
        "error_type": type(error).__name__,
        "error": str(error)[:300],
        "blocked": [],
        "applied": False,
    }
    grading_result["runtime_gate_error"] = err
    try:
        criteria = grading_result.get("criteria_results")
        if not isinstance(criteria, list) or not criteria:
            return err
        if not _looks_like_game_fail_safe(grading_result, artifact_inventory):
            err["reason"] = "not_a_game_submission"
            return err

        for row in criteria:
            if not isinstance(row, dict):
                continue
            short = _short_level(str(row.get("criteria_level") or ""))
            if short not in _FAIL_CLOSED_SHORT:
                continue
            if short == "D3" and (row.get("achieved") or row.get("awardable")):
                row.setdefault("pre_gate_state", _row_state(row))
            if short == "D3":
                row["dependency_blocked_by"] = "gate_error"
            was_awarding = bool(row.get("achieved") or row.get("awardable"))
            row["runtime_gate_block"] = True
            _demote_row(row, _GATE_ERROR_REASON_AR)
            row["awardable"] = False
            row["achievement_authority"] = _GATE_ERROR_AUTHORITY
            row["award_block_reason"] = "runtime_gate_error"
            row["award_block_reason_ar"] = _GATE_ERROR_REASON_AR
            if was_awarding:
                err["blocked"].append(str(row.get("criteria_level")))

        err["prior"] = {
            key: grading_result.get(key)
            for key in ("grade_decision_status", "official_grade_provisional",
                        "evidence_required", "grade_level_provisional")
        }
        _recompute_grade(grading_result)
        grading_result["grade_level_provisional"] = grading_result.get("grade_level")
        grading_result["grade_decision_status"] = "NOT_VERIFIED"
        grading_result["official_grade_provisional"] = True
        grading_result["evidence_required"] = "AUTOMATED_VERIFICATION_INCOMPLETE"
        for stale_key in ("institutional_resolution", "grade_display_metrics",
                          "btec_institutional_award", "expected_runtime_grade",
                          "institutional_grade_display", "btec_grade_level"):
            grading_result.pop(stale_key, None)
        err["applied"] = True
    except Exception as inner:  # pragma: no cover - the fallback must never raise
        err["fallback_error"] = f"{type(inner).__name__}: {str(inner)[:200]}"
    return err


def _enforce_d3_dependency(criteria: Sequence[Dict[str, Any]]) -> List[str]:
    """Row-level ``M3 blocked → D3 blocked`` (BTEC: Distinction needs every Merit).

    D3 is not a runtime mechanic, so the gate never *awards* it; it only refuses to
    leave D3 achieved while M3 is not.  The block is recorded on the D3 row
    (``dependency_blocked_by`` + ``award_block_reason``) and reversed if M3 later
    passes and the row had been achieved before the block.
    """
    rows = [r for r in criteria if isinstance(r, dict)]
    m3 = next((r for r in rows if _short_level(str(r.get("criteria_level") or "")) == "M3"), None)
    if m3 is None:
        return []
    m3_ok = bool(m3.get("achieved")) and m3.get("awardable") is not False and not m3.get("runtime_gate_block")
    changes: List[str] = []
    for row in rows:
        if _short_level(str(row.get("criteria_level") or "")) != "D3":
            continue
        level = row.get("criteria_level")
        blocked_by = row.get("dependency_blocked_by")
        if not m3_ok:
            reason_ar = "لم يتحقق C.M3 (أو حُجب)، ولا يُمنح C.D3 دون تحقق كل معايير Merit."
            if row.get("achieved") or row.get("awardable"):
                row.setdefault("pre_gate_state", _row_state(row))
                _demote_row(row, reason_ar)
                row["awardable"] = False
                row["dependency_blocked_by"] = "M3"
                row["award_block_reason"] = "dependency_m3_not_met"
                row["award_block_reason_ar"] = reason_ar
                changes.append(f"{level}:dependency_blocked_by_M3")
            elif blocked_by == "gate_error":
                # The gate recovered but M3 still is not awardable: the reason is now M3.
                row["dependency_blocked_by"] = "M3"
                row["award_block_reason"] = "dependency_m3_not_met"
                row["award_block_reason_ar"] = reason_ar
                if row.get("achievement_authority") == _GATE_ERROR_AUTHORITY:
                    row.pop("achievement_authority", None)
                row.pop("runtime_gate_block", None)
        elif blocked_by in ("M3", "gate_error"):
            # M3 passes now: lift only OUR block, restoring the state we recorded.
            row.pop("dependency_blocked_by", None)
            row.pop("award_block_reason", None)
            row.pop("award_block_reason_ar", None)
            row.pop("runtime_gate_block", None)
            if row.get("achievement_authority") == _GATE_ERROR_AUTHORITY:
                row.pop("achievement_authority", None)
            prior = row.pop("pre_gate_state", None)
            if isinstance(prior, dict) and prior.get("achieved"):
                row["achieved"] = True
                row["score"] = max(int(row.get("score") or 0), int(prior.get("score") or 0))
                row["verdict_status"] = prior.get("verdict_status") or "pass"
                row["awardable"] = True
                row.pop("governance_adjustment_ar", None)
                changes.append(f"{level}:dependency_block_lifted")
    return changes


def is_game_submission(
    inventory: Optional[Dict[str, Any]],
    *,
    submission_paths: Optional[List[str]] = None,
) -> bool:
    """True when the submission is a runnable game project (any supported engine).

    Non-game assignments (networking, spreadsheets, essays, …) are never gated."""
    inv = inventory or {}
    rt = inv.get("runtime_artifacts") or {}
    if (
        rt.get("scratch_detected")
        or rt.get("gamemaker_detected")
        or rt.get("gamemaker_build_detected")
        or rt.get("godot_export_detected")
        or rt.get("unity_build_detected")
        or rt.get("html5_build_detected")
    ):
        return True
    if inv.get("has_executable_artifacts"):
        # executable_artifacts that are game builds (Scratch/exe/pck/apk/win)
        return True
    paths = list(submission_paths or []) + _collect_paths(None, inv)
    joined = "\n".join(paths).lower().replace("\\", "/")
    if joined and (has_runnable_game_project(joined) or detect_engine_from_text(joined)):
        return True
    return False


def evaluate_runtime_evidence(
    inventory: Optional[Dict[str, Any]],
    *,
    submission_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return the canonical runtime-evidence *path* verdict for a submission.

    Reuses ``assess_playtest_evidence`` (the established accepted-evidence union:
    L5 human playtest, gameplay video, runtime+gameplay validation, human review).

    ``satisfied`` means "some runtime-related evidence exists".  It is not a claim
    that the game was run, and not criterion awardability — see the module docstring.
    """
    inv = inventory or {}
    try:
        from app.pro_engine_gameplay_governance import assess_playtest_evidence

        assessment = assess_playtest_evidence(inv, submission_paths=submission_paths)
    except Exception as err:  # pragma: no cover - defensive
        return {
            "version": GATE_VERSION,
            "status": "UNKNOWN",
            "satisfied": False,
            "error": str(err),
            "accepted_evidence": [],
            "paths": {},
        }

    paths = assessment.get("playtest_paths") or {}
    satisfied = bool(assessment.get("any_path_satisfied"))
    accepted: List[str] = [k for k, v in paths.items() if v]
    return {
        "version": GATE_VERSION,
        "status": "PASS" if satisfied else "BLOCKED",
        "satisfied": satisfied,
        "engine_id": assessment.get("engine_id"),
        "accepted_evidence": accepted,
        "paths": paths,
        "structure_only_runtime": assessment.get("structure_only_runtime"),
        "summary_ar": assessment.get("summary_ar"),
    }


def _recompute_grade(grading_result: Dict[str, Any]) -> None:
    criteria = grading_result.get("criteria_results") or []
    grading_result["grade_level"] = determine_grade_level(criteria)
    total = sum(int(r.get("score") or 0) for r in criteria if isinstance(r, dict))
    pct = int(total / (len(criteria) or 1))
    grading_result["percentage"] = pct
    grading_result["total_score"] = pct
    grading_result["criteria_score_pct"] = pct


def apply_runtime_evidence_gate(
    grading_result: Dict[str, Any],
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Terminal seal: block runtime-dependent criteria lacking real runtime evidence.

    Idempotent — safe to call multiple times across the pipeline / read paths.
    Returns a report dict (also stored at ``grading_result['runtime_evidence_gate']``).
    """
    criteria = grading_result.get("criteria_results")
    if not isinstance(criteria, list) or not criteria:
        return {"applied": False, "reason": "no_criteria"}

    _clear_runtime_gate_error(grading_result)
    inv = artifact_inventory or grading_result.get("artifact_inventory") or {}
    # The terminal gate is also called on report/read paths.  Resolve engine
    # adapter nesting here so a GameMaker GV stored under platform_analyses is
    # not silently downgraded to an empty/L3 shell at the final decision layer.
    try:
        from app.gameplay_verifier import sync_authoritative_gv

        sync_authoritative_gv(inv, grading_result)
        inv = grading_result.get("artifact_inventory") or inv
    except Exception:
        pass
    submission_paths = _collect_paths(grading_result, inv)

    if not is_game_submission(inv, submission_paths=submission_paths):
        report = {
            "applied": False,
            "version": GATE_VERSION,
            "reason": "not_a_game_submission",
        }
        grading_result["runtime_evidence_gate"] = report
        return report

    verdict = evaluate_runtime_evidence(inv, submission_paths=submission_paths)

    gv = inv.get("gameplay_verification") or {}
    obs = inv.get("runtime_observation_report") or {}
    if not gv:
        gv = grading_result.get("gameplay_verification") or {}
    if not gv:
        gv = obs.get("gameplay_verification") or {}
    if not gv:
        for analysis in obs.get("artifact_analyses") or []:
            if isinstance(analysis, dict) and isinstance(analysis.get("gameplay_verification"), dict):
                gv = analysis["gameplay_verification"]
                break
    smoke = (inv.get("runtime_validation") or obs.get("runtime_validation") or {}).get(
        "functional_smoke"
    ) or {}
    automated_gate: Dict[str, Any] = {}
    code_diff = _compute_m3_code_diff(grading_result, criteria, submission_paths)
    try:
        from app.gameplay_verifier import (
            _test_document_present,
            assess_automated_l4_gate,
            count_test_document_entries,
        )

        inv_for_docs = {
            **inv,
            "intake_relative_paths": grading_result.get("intake_relative_paths")
            or inv.get("intake_relative_paths")
            or [],
        }
        # The gameplay verifier owns direct and source+runtime proof; the
        # checklist owns applicability.  Pass both to the final criterion gate
        # so it evaluates every required feature instead of a mechanic count.
        gv_for_gate = dict(gv)
        gv_for_gate["requirement_checklist"] = (
            grading_result.get("requirement_checklist")
            or inv.get("requirement_checklist")
            or {}
        )
        gv_for_gate["runtime_evidence_package"] = (
            grading_result.get("runtime_evidence_package")
            or inv.get("runtime_evidence_package")
            or {}
        )
        automated_gate = assess_automated_l4_gate(
            gv_for_gate,
            test_document_present=_test_document_present(inv_for_docs),
            test_doc_entries=count_test_document_entries(inv_for_docs),
            functional_smoke_pass=smoke.get("functional_smoke_pass") is True,
            grading_mode=grading_result.get("grading_mode") or inv.get("grading_mode"),
            criteria_results=criteria,
            engine_id=verdict.get("engine_id"),
            student_text=str(grading_result.get("student_text") or ""),
            code_diff=code_diff,
        )
    except Exception as gate_err:
        # Fail closed: an empty verdict means no criterion passes (rows are demoted
        # below).  Keep the reason visible instead of swallowing it.
        automated_gate = {"error": f"{type(gate_err).__name__}: {str(gate_err)[:200]}"}
    criterion_pass = dict(automated_gate.get("criterion_pass") or {})
    # Runtime evidence must be tied to an identifiable version/build/source: an
    # unattributable run never opens P5/P6/M3 (NOT VERIFIED, not a failure).
    from app.runtime_provenance_gate import evaluate_provenance_binding

    provenance_binding = evaluate_provenance_binding(grading_result)
    for _short in provenance_binding["blocked"]:
        criterion_pass[_short] = False

    changes: List[str] = []
    if not verdict["satisfied"]:
        for row in criteria:
            if not isinstance(row, dict):
                continue
            short = _short_level(str(row.get("criteria_level") or ""))
            if short not in RUNTIME_GATED_SHORT:
                continue
            if criterion_pass.get(short):
                row.pop("runtime_gate_block", None)
                row.pop("achievement_authority", None)
                if row.get("award_block_reason") == "runtime_not_verified":
                    row.pop("award_block_reason", None)
                    row.pop("award_block_reason_ar", None)
                row["awardable"] = True
                row["runtime_l4_verified"] = True
                _promote_l4_gate_row(row)
                changes.append(f"{row.get('criteria_level')}:runtime_gate_l4_open")
                continue
            # Record a change only when this row was actually awarding something.
            was_awarding = bool(row.get("achieved") or row.get("awardable"))
            # Always stamp the hold flag so promotion paths can never re-award,
            # even if a prior layer left the row achieved.
            row["runtime_gate_block"] = True
            gate_reason_ar = _gate_reason_for(gv)
            _demote_row(row, gate_reason_ar)  # no-op if already not achieved
            row["awardable"] = False
            row["achievement_authority"] = _RUNTIME_GATE_AUTHORITY
            row["award_block_reason"] = "runtime_not_verified"
            row["award_block_reason_ar"] = gate_reason_ar
            if was_awarding:
                changes.append(f"{row.get('criteria_level')}:runtime_gate_block")
    else:
        # Runtime satisfied — clear stale holds and align L4-certified criteria.
        decisions_by_short = {
            str(d.get("criterion") or ""): d
            for d in (automated_gate.get("decisions") or [])
            if isinstance(d, dict)
        }
        for row in criteria:
            if not isinstance(row, dict):
                continue
            if row.get("runtime_gate_block"):
                row.pop("runtime_gate_block", None)
            short = _short_level(str(row.get("criteria_level") or ""))
            if short in RUNTIME_GATED_SHORT and criterion_pass.get(short):
                _promote_l4_gate_row(row, decision=decisions_by_short.get(short))
                row["awardable"] = True
                changes.append(f"{row.get('criteria_level')}:runtime_satisfied_l4_open")
            elif short in RUNTIME_GATED_SHORT:
                decision = decisions_by_short.get(short) or {}
                was_awarding = bool(row.get("achieved") or row.get("awardable"))
                reason_ar = str(
                    decision.get("reason_ar")
                    or "لم تثبت كل ميزات اللعبة المطلوبة بالتشغيل أو بتحقق الكود المقترن بالتشغيل"
                )
                row["runtime_gate_block"] = True
                _demote_row(row, reason_ar)
                row["awardable"] = False
                row["achievement_authority"] = _RUNTIME_GATE_AUTHORITY
                row["award_block_reason"] = str(
                    decision.get("reason") or "required_gameplay_features_unverified"
                )
                row["award_block_reason_ar"] = reason_ar
                row.pop("pro_gameplay_governance_hold", None)
                row.pop("engine_governance_engine", None)
                if was_awarding:
                    changes.append(f"{row.get('criteria_level')}:required_feature_gate_block")

    for row in criteria:
        if not isinstance(row, dict):
            continue
        info = provenance_binding["blocked"].get(_short_level(str(row.get("criteria_level") or "")))
        if info:
            row["runtime_gate_block"] = True
            row["awardable"] = False
            row["award_block_reason"] = "provenance_unverified"
            row["award_block_reason_ar"] = (
                "لا يمكن ربط دليل التشغيل بنسخة/بناء محدّدين "
                f"({info['code']}) — غير مُتحقَّق منه وليس فشلاً للطالب."
            )
            row["provenance_binding"] = info

    changes.extend(_enforce_d3_dependency(criteria))

    if changes:
        _recompute_grade(grading_result)
        if any("runtime_satisfied_l4_open" in change for change in changes):
            _align_overall_feedback_after_runtime_open(grading_result)
        # Single source of truth: invalidate cached grade-display objects so every
        # downstream reader (UI, Word, PDF, API) re-derives from the gated grade_level
        # instead of a stale higher band (prevents "UI=U but report=M").
        for stale_key in (
            "institutional_resolution",
            "grade_display_metrics",
            "btec_institutional_award",
            "expected_runtime_grade",
            "institutional_grade_display",
            "btec_grade_level",
        ):
            grading_result.pop(stale_key, None)

    report = {
        "applied": bool(changes),
        "version": GATE_VERSION,
        "runtime_status": verdict["status"],
        "satisfied": verdict["satisfied"],
        "accepted_evidence": verdict.get("accepted_evidence"),
        "engine_id": verdict.get("engine_id"),
        "gated_criteria": sorted(RUNTIME_GATED_SHORT),
        "changes": changes,
        "automated_l4_gate": automated_gate,
        "m3_code_diff": _code_diff_summary(code_diff),
        "summary_ar": verdict.get("summary_ar"),
    }
    grading_result["runtime_evidence_gate"] = report
    return report
