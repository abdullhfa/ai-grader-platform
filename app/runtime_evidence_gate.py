"""
Runtime Evidence Gate — Pearson-grade single authority for runtime-dependent criteria.

Golden rule (PRO governance):
    A runtime-dependent criterion (C.P5 / C.P6 / C.M3 / C.D3) may NOT be awarded
    unless the game was *actually* shown to run / be played. Documents, slides,
    images, AI description, static analysis (incl. Scratch static graph), and the
    mere *presence* of a project/.sb3/.exe are NOT sufficient on their own.

Accepted runtime evidence (any ONE satisfies the gate):
    1. Runtime PASS         — real launch + gameplay validation (engine sandbox)
    2. Gameplay video       — documented gameplay footage
    3. Human review (L5)    — teacher-verified / visually-corroborated playtest
    4. Human review recorded

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


@dataclass(frozen=True)
class GateRule:
    """Per-criterion gate policy (Option C — spec §1.2)."""

    criterion: str
    automatic: bool
    teacher_confirmation_required: bool
    min_l4_level: str = "L4_partial"
    min_test_doc_entries: int = 0


DEFAULT_GATE_RULES: tuple[GateRule, ...] = (
    GateRule("P5", automatic=True, teacher_confirmation_required=False, min_l4_level="L4_partial"),
    GateRule(
        "P6",
        automatic=True,
        teacher_confirmation_required=False,
        min_l4_level="L4_partial",
        min_test_doc_entries=2,
    ),
    GateRule(
        "M3",
        automatic=False,
        teacher_confirmation_required=True,
        min_l4_level="L4_full",
    ),
    GateRule(
        "D3",
        automatic=False,
        teacher_confirmation_required=True,
        min_l4_level="L4_full",
    ),
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
                    teacher_confirmation_required=rule.teacher_confirmation_required,
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
    teacher_confirmation_required: bool
    teacher_confirmed: bool = False
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
            "teacher_confirmation_required": self.teacher_confirmation_required,
            "teacher_confirmed": self.teacher_confirmed,
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
    row: Optional[Dict[str, Any]], criterion: str
) -> Dict[str, Any]:
    """Verify higher-band academic evidence without relying on a human flag.

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
        teacher_confirmed: Optional[Dict[str, bool]] = None,
        functional_smoke_pass: bool = False,
        criteria_results: Optional[Sequence[Dict[str, Any]]] = None,
        engine_id: Optional[str] = None,
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
        teacher_confirmed = teacher_confirmed or {}
        evidence_pkg = gv.get("evidence_package") or {}
        req_results = evidence_pkg.get("results") or []
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

            confirmed = bool(teacher_confirmed.get(rule.criterion))
            l4_ok = self._l4_satisfies(l4, rule.min_l4_level)
            test_ok = test_doc_entries >= rule.min_test_doc_entries
            runtime_ok = functional_smoke_pass or gameplay_entered or movement
            gamemaker_ai_higher_band = engine.startswith("gamemaker") and rule.criterion in {
                "M3",
                "D3",
            }
            academic = (
                _assess_ai_academic_evidence(
                    criteria_by_short.get(rule.criterion), rule.criterion
                )
                if gamemaker_ai_higher_band
                else {"verified": False, "confidence": 0.0, "checks": {}, "marker_hits": []}
            )
            effective_automatic = rule.automatic or gamemaker_ai_higher_band
            effective_teacher_required = (
                rule.teacher_confirmation_required and not gamemaker_ai_higher_band
            )

            if gamemaker_ai_higher_band:
                # GameMaker higher bands are decided by a composite automated proof:
                # full runtime/gameplay, a test record, and the AI academic evidence.
                test_ok = test_doc_entries >= max(1, rule.min_test_doc_entries)
                prerequisite_ok = (
                    criterion_pass.get("M3") is True if rule.criterion == "D3" else True
                )
                open_gate = bool(
                    l4_ok
                    and runtime_ok
                    and test_ok
                    and academic.get("verified")
                    and prerequisite_ok
                )
                chain.extend(
                    [
                        f"ai_academic_verified={bool(academic.get('verified'))}",
                        f"ai_verification_confidence={academic.get('confidence', 0.0):.2f}",
                        f"test_document_verified={test_ok}",
                        f"prerequisite_verified={prerequisite_ok}",
                    ]
                )
                if open_gate:
                    reason = "automatic_ai_runtime_composite"
                    reason_ar = (
                        "تحقق آلي كامل: تحليل أكاديمي بالذكاء الاصطناعي + "
                        "تشغيل GameMaker فعلي L4 + سجل اختبار"
                    )
                elif not l4_ok or not runtime_ok:
                    reason = "automated_runtime_evidence_insufficient"
                    reason_ar = "لم تكفِ أدلة تشغيل GameMaker الآلية لهذا المعيار"
                elif not test_ok:
                    reason = "automated_test_evidence_insufficient"
                    reason_ar = "لم يرصد النظام سجل اختبار كافياً للتحقق الآلي"
                elif not prerequisite_ok:
                    reason = "automated_prerequisite_not_met"
                    reason_ar = "لم يتحقق C.M3 آلياً، لذلك لا يمكن فتح C.D3"
                else:
                    reason = "automated_academic_evidence_insufficient"
                    reason_ar = "لم تستوفِ الأدلة الأكاديمية شروط التحقق الآلي لهذا المعيار"
            elif rule.teacher_confirmation_required:
                open_gate = confirmed and l4_ok and runtime_ok
                reason = "teacher_confirmation_required"
                reason_ar = (
                    "يتطلب تأكيد المعلم — لا يُفتح تلقائياً في PRO"
                    if not confirmed
                    else "تأكيد المعلم مسجّل"
                )
            else:
                open_gate = l4_ok and runtime_ok and test_ok
                if rule.criterion == "P5":
                    open_gate = open_gate and (movement or mechanics >= 1)
                reason = "automatic_l4" if open_gate else "evidence_insufficient"
                reason_ar = (
                    f"بوابة تلقائية — L4 {l4}"
                    if open_gate
                    else "أدلة L4 غير كافية لفتح البوابة"
                )
                if rule.min_test_doc_entries and not test_ok:
                    reason_ar = (
                        f"يتطلب ≥{rule.min_test_doc_entries} مدخلات وثائق اختبار "
                        f"(موجود: {test_doc_entries})"
                    )

            if shots >= 1:
                chain.append(f"gameplay_window_screenshots={shots}")

            decision = GateDecision(
                criterion=rule.criterion,
                open=open_gate,
                automatic=effective_automatic,
                teacher_confirmation_required=effective_teacher_required,
                teacher_confirmed=confirmed,
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
            "higher_band_verification": "automated_ai" if engine.startswith("gamemaker") else "policy_default",
            "summary_ar": (
                f"L4 آلي ({l4}) — ميكانيكا={mechanics} لقطات={shots}"
                if l4_partial or l4_full
                else "L3 — إطلاق بدون gameplay مؤكد"
            ),
        }


# Runtime-dependent criteria (per Pearson policy): prototype, testing, refinement
# merit, and the corresponding distinction band. Matches user spec C.P5/C.P6/C.M3/C.D3.
RUNTIME_GATED_SHORT = frozenset({"P5", "P6", "M3", "D3"})

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
    "(Gameplay). لتحقيق C.P5/C.P6/C.M3/C.D3 يجب تقديم أدلة تشغيل واضحة من داخل "
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
    if short in {"M3", "D3"}:
        row["achievement_authority"] = "AI_RUNTIME_COMPOSITE"
        row["ai_verification"] = {
            "status": "verified",
            "automatic": True,
            "human_review_required": False,
            "confidence": float((decision or {}).get("ai_verification_confidence") or 0.0),
            "method": "academic_ai_plus_gamemaker_l4_runtime",
        }
        academic_snapshot = row.get("academic_snapshot")
        if isinstance(academic_snapshot, dict):
            academic_snapshot["human_review_required"] = {
                "required": False,
                "severity": "none",
                "reasons": ["resolved_by_automated_ai_runtime_composite"],
            }
            academic_snapshot["review_confidence"] = 1.0
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
            "تحقق C.M3 آلياً دون تدخل بشري: أكد تحليل الذكاء الاصطناعي فعالية "
            "العرض والتوثيق، وأثبت تشغيل GameMaker بمستوى L4_full عمل النموذج "
            "الأولي والميكانيكا، مع وجود سجل اختبار مرتبط."
        )
    elif short == "D3":
        row["feedback"] = (
            "تحقق C.D3 آلياً دون تدخل بشري: أكد تحليل الذكاء الاصطناعي أن العرض "
            "مقنع وشامل ويتضمن تحليلاً نقدياً وتبريراً مدعوماً بالبيانات، وأثبت "
            "تشغيل GameMaker بمستوى L4_full فعالية النموذج الأولي."
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
    """Return the canonical runtime-evidence verdict for a submission.

    Reuses ``assess_playtest_evidence`` (the established accepted-evidence union:
    L5 human playtest, gameplay video, runtime+gameplay validation, human review).
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
        teacher_confirmed = {}
        l5 = inv.get("l5_human_playtest") or grading_result.get("l5_human_playtest") or {}
        if l5.get("status") in ("complete_visual", "confirmed"):
            teacher_confirmed = {"M3": True, "D3": True}
        automated_gate = assess_automated_l4_gate(
            gv,
            test_document_present=_test_document_present(inv_for_docs),
            test_doc_entries=count_test_document_entries(inv_for_docs),
            functional_smoke_pass=smoke.get("functional_smoke_pass") is True,
            teacher_confirmed=teacher_confirmed,
            grading_mode=grading_result.get("grading_mode") or inv.get("grading_mode"),
            criteria_results=criteria,
            engine_id=verdict.get("engine_id"),
        )
    except Exception:
        automated_gate = {}
    criterion_pass = automated_gate.get("criterion_pass") or {}

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
            elif short in ("M3", "D3") and short in RUNTIME_GATED_SHORT:
                decision = decisions_by_short.get(short) or {}
                row["awardable"] = False
                row["achievement_authority"] = "HUMAN_REVIEW_REQUIRED"
                row["award_block_reason"] = "teacher_confirmation_required"
                row["award_block_reason_ar"] = str(
                    decision.get("reason_ar")
                    or "يتطلب تأكيد المعلم — لا يُفتح تلقائياً في PRO"
                )
                row["feedback"] = (
                    "لم يتحقق المعيار تلقائياً. تم التحقق من تشغيل اللعبة والـ gameplay "
                    "بمستوى L4، لكن هذا المعيار الأعلى يتطلب تأكيد المعلم ومراجعة "
                    "الأدلة التحليلية/التقييمية الخاصة به."
                )
                row.pop("pro_gameplay_governance_hold", None)
                row.pop("engine_governance_engine", None)

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
        "summary_ar": verdict.get("summary_ar"),
    }
    grading_result["runtime_evidence_gate"] = report
    return report
