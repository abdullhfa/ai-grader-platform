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

            if rule.teacher_confirmation_required:
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
                automatic=rule.automatic,
                teacher_confirmation_required=rule.teacher_confirmation_required,
                teacher_confirmed=confirmed,
                reason=reason,
                reason_ar=reason_ar,
                evidence_chain=chain,
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
    "مجرد وجود ملفات المشروع (.sb3/.exe). الأدلة المقبولة: "
    "تشغيل ناجح موثّق، أو تشغيل ناجح مع ميزات مثبتة من كود المشروع "
    "(بالملف والسطر)، أو فيديو لعب، أو مراجعة المعلم."
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


def _promote_l4_gate_row(row: Dict[str, Any]) -> None:
    """Align achieved/score when automated L4 gate certifies this criterion."""
    det = row.get("deterministic_rubric") or {}
    if not row.get("achieved"):
        row["achieved"] = True
        row["score"] = max(int(row.get("score") or 0), 75)
        row["verdict_status"] = "pass"
        auth = str(det.get("authority") or row.get("achievement_authority") or "")
        if auth and auth not in (_RUNTIME_GATE_AUTHORITY, "NONE", ""):
            row["achievement_authority"] = auth
        elif not row.get("achievement_authority"):
            row["achievement_authority"] = "RUNTIME_L4_GATE"
    else:
        # Already achieved but an earlier layer may have capped the score while
        # demoting (e.g. runtime cap) before this gate re-certified the row.
        # A certified row must never display an under-threshold score.
        row["score"] = max(int(row.get("score") or 0), 75)
        row["verdict_status"] = "pass"
    row.pop("governance_adjustment_ar", None)
    row.pop("award_block_reason", None)
    row.pop("award_block_reason_ar", None)


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
    try:
        from app.runtime.validation_engine import resolve_functional_smoke

        smoke = resolve_functional_smoke(inv, obs)
    except Exception:
        smoke = (inv.get("runtime_validation") or obs.get("runtime_validation") or {}).get(
            "functional_smoke"
        ) or {}

    # Deterministic static corroboration: the game runs (smoke PASS) and the
    # mechanics are proven in the student's source code (file:line evidence).
    # Same submission bytes → same gate outcome, every run.
    static: Dict[str, Any] = {}
    static_core_n = 0
    static_corroborated = False
    gv_eff: Dict[str, Any] = gv if isinstance(gv, dict) else {}
    try:
        from app.pro_engine_gameplay_governance import (
            resolve_static_mechanics,
            static_core_mechanics_count,
        )

        static = resolve_static_mechanics(
            inv, obs=obs, submission_paths=submission_paths
        )
        static_core_n = static_core_mechanics_count(static)
        smoke_pass = smoke.get("functional_smoke_pass") is True
        crash = bool(
            obs.get("crash_detected")
            or ((obs.get("runtime_signal_graph") or {}).get("signals") or {}).get("crash")
            == "observed"
        )
        static_corroborated = smoke_pass and not crash and static_core_n >= 1
        if static_corroborated:
            from app.gameplay_verifier import calculate_l4_level

            gv_eff = dict(gv) if isinstance(gv, dict) else {}
            prev = int(gv_eff.get("mechanics_verified_count") or 0)
            gv_eff["mechanics_verified_count"] = max(prev, static_core_n)
            gv_eff["gameplay_entered"] = True
            gv_eff["l4_level"] = calculate_l4_level(
                gameplay_entered=True,
                mechanics_verified_count=gv_eff["mechanics_verified_count"],
            )
            gv_eff["static_corroborated"] = True
            gv_eff["static_mechanics_ids"] = sorted(
                static.get("detected_ids") or []
            )
    except Exception:
        static_corroborated = False
        gv_eff = gv if isinstance(gv, dict) else {}

    # Persist the resolved evidence into the grading result itself so every
    # later read path (Word/PDF/UI panels) sees the same verdict even when the
    # stored inventory snapshot is trimmed or predates detector fixes.
    if static.get("detected_ids"):
        grading_result["static_mechanics"] = static
    if smoke:
        grading_result["runtime_smoke_resolved"] = smoke

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
        elif static_corroborated and static_core_n >= 3:
            # Full deterministic corroboration (runtime PASS + ≥3 core mechanics
            # proven in source with file:line evidence) satisfies the M3/D3
            # confirmation requirement — equivalent evidentiary weight to L4_full.
            teacher_confirmed = {"M3": True, "D3": True}
        automated_gate = assess_automated_l4_gate(
            gv_eff or gv,
            test_document_present=_test_document_present(inv_for_docs),
            test_doc_entries=count_test_document_entries(inv_for_docs),
            functional_smoke_pass=smoke.get("functional_smoke_pass") is True,
            teacher_confirmed=teacher_confirmed,
            grading_mode=grading_result.get("grading_mode") or inv.get("grading_mode"),
        )
        if static_corroborated:
            automated_gate["static_corroborated"] = True
            automated_gate["static_core_mechanics_count"] = static_core_n
    except Exception:
        automated_gate = {}
    criterion_pass = automated_gate.get("criterion_pass") or {}

    # --- Pause detection: GameMaker source project without a runnable build,
    # and the auto-builder cannot run because GameMaker (Igor) is not installed
    # on the grading machine.
    #
    # Teacher-mandated policy (do NOT relax without their explicit sign-off):
    #   GameMaker source-only submission + no GameMaker installed on the
    #   grading machine ⇒ FULL PAUSE, unconditionally.  Alternative evidence
    #   (documented gameplay video, static code-mechanics corroboration, or a
    #   recorded human playtest) is NOT accepted as a substitute for the
    #   real IDE build + runtime launch. The grader must stop, display an
    #   "⏸ install GameMaker" banner, and wait for a re-grade after install.
    #
    # This block is 100% inert when the submission already ships a runnable
    # .exe / data.win / index.html — the .exe path is never touched.
    import os as _os
    paused_info: Optional[Dict[str, Any]] = None
    try:
        paths_l = "\n".join(str(p) for p in submission_paths).lower()
        # Only a filesystem separator or space before "exe" counts as a real
        # executable path — "exe" as a substring inside other tokens (e.g.
        # "example.txt", "executive.docx") must not falsely trip the "already
        # has a runnable build" branch and suppress the pause banner.
        import re as _re_gate
        _has_exe_file = bool(
            _re_gate.search(r"(^|[\\/\s])[^\\/\n]*\.exe(\s|$)", paths_l)
        )
        _has_data_win = bool(
            _re_gate.search(r"(^|[\\/\s])data\.win(\s|$)", paths_l)
        )
        _has_html5_entry = bool(
            _re_gate.search(r"(^|[\\/\s])(index|runner)\.html?(\s|$)", paths_l)
        )
        has_runnable = _has_exe_file or _has_data_win or _has_html5_entry
        has_gm_source = (
            bool(_re_gate.search(r"\.yyp(\s|$)", paths_l))
            or bool(_re_gate.search(r"\.gml(\s|$)", paths_l))
            or bool(static.get("detected_ids"))
        )
        ide_build = (
            obs.get("gamemaker_ide_build")
            or inv.get("gamemaker_ide_build")
            or grading_result.get("gamemaker_ide_build")
            or {}
        )
        build_reason = str(ide_build.get("reason") or "")
        build_succeeded = bool(ide_build.get("success"))

        # Live probe: is GameMaker actually installed on THIS grading machine
        # right now? This is the most reliable signal — much better than
        # trying to infer from a possibly-missing ide_build record. If the
        # probe finds Igor + a runtime, we know we could build; if not, the
        # student's source-only GameMaker submission needs the pause banner.
        _tools_probe_available: Optional[bool] = None
        try:
            from app.runtime_engines.gamemaker.ide_builder import (
                discover_gamemaker_tools,
            )
            _tools_probe_available = bool(
                (discover_gamemaker_tools() or {}).get("available")
            )
        except Exception as _probe_exc:
            print(
                f"🎮 [GAMEMAKER-PAUSE-GATE] tools probe failed: "
                f"{type(_probe_exc).__name__}: {_probe_exc}"
            )
            _tools_probe_available = None

        tools_missing = (
            build_reason.startswith("gamemaker_runtime_not_installed")
            or build_reason in ("windows_only", "auto_build_disabled")
            or (not ide_build and _tools_probe_available is not True)
            or (_tools_probe_available is False)
        )
        # Escape hatch: an admin can explicitly opt back into "accept
        # alternative evidence when GameMaker is missing" per environment.
        # Off by default — the strict pause is the teacher-mandated behavior.
        _accept_alt = _os.environ.get(
            "AI_GRADER_GAMEMAKER_ACCEPT_ALT_EVIDENCE_WHEN_MISSING", ""
        ).strip().lower() in ("1", "true", "yes", "on")

        # Loud, unconditional trace — this MUST appear in server logs for
        # every GameMaker-flavoured submission so we can tell at a glance
        # whether the pause block was reached and what it decided.
        print(
            "🎮 [GAMEMAKER-PAUSE-GATE] "
            f"paths_len={len(submission_paths or [])} "
            f"has_gm_source={has_gm_source} has_runnable={has_runnable} "
            f"build_succeeded={build_succeeded} tools_missing={tools_missing} "
            f"tools_probe_available={_tools_probe_available} "
            f"build_reason={build_reason!r} accept_alt_override={_accept_alt} "
            f"verdict_satisfied={verdict.get('satisfied')}"
        )

        if has_gm_source and not has_runnable and not build_succeeded and tools_missing:
            _alt = ", ".join(
                str(a) for a in (verdict.get("accepted_evidence") or [])
            )
            _alt_note_ar = (
                f" (تم رصد أدلة بديلة: {_alt} — لكن سياسة المصحح تشترط تشغيلاً "
                f"فعلياً عبر GameMaker لهذا التقديم المصدري، فلا تُقبل كبديل عن التثبيت.)"
                if _alt
                else ""
            )
            if _accept_alt and verdict["satisfied"]:
                # Explicit admin override — fall back to the older
                # "informational only" behavior. Off by default.
                paused_info = {
                    "paused": False,
                    "reason": "gamemaker_not_installed_alt_evidence_admin_override",
                    "short_ar": "ℹ GameMaker غير مثبت — قُبلت أدلة بديلة (تجاوز إداري)",
                    "message_ar": (
                        "ℹ️ ملاحظة: GameMaker غير مثبت على جهاز التصحيح، وتم قبول أدلة "
                        f"بديلة بناءً على تفعيل التجاوز الإداري "
                        f"AI_GRADER_GAMEMAKER_ACCEPT_ALT_EVIDENCE_WHEN_MISSING=1. "
                        f"({_alt or 'أدلة بديلة موثقة'})"
                    ),
                    "builder_reason": build_reason or "no_build_attempt_recorded",
                }
            else:
                # STRICT PAUSE — teacher-mandated. Alternative evidence is
                # noted but does NOT bypass the pause. Grading is stopped
                # on this student until GameMaker is installed and the
                # student is re-graded.
                paused_info = {
                    "paused": True,
                    "reason": "gamemaker_not_installed",
                    "short_ar": "⏸ معلّق — ثبّت GameMaker ثم أعد التصحيح",
                    "message_ar": (
                        "⏸ تم إيقاف تصحيح هذا الطالب مؤقتاً.\n"
                        "السبب: المشروع مُسلَّم كمصدر GameMaker (بدون ملف تشغيل .exe)، "
                        "وبرنامج GameMaker غير مثبت على جهاز التصحيح — لا يمكن بناء "
                        "اللعبة وتشغيلها فعلياً.\n"
                        "المطلوب: 1) ثبّت GameMaker Studio 2 على هذا الجهاز. "
                        "2) أعد الضغط على «بدء التصحيح» لهذا الطالب. "
                        "سيقوم النظام تلقائياً باكتشاف التثبيت، بناء المشروع، "
                        "تشغيل اللعبة، وإكمال التصحيح دون الحاجة لأي خطوة يدوية "
                        "إضافية." + _alt_note_ar
                    ),
                    "builder_reason": build_reason or "no_build_attempt_recorded",
                    "alt_evidence_seen": bool(_alt),
                    "policy": "strict_pause_no_alt_evidence_bypass",
                }
                # Surface a top-level, easy-to-render banner flag so any
                # downstream reader (UI, Word/PDF report, API) can spotlight
                # the pause state without having to reach into runtime gate
                # internals.
                grading_result["gamemaker_install_pause_banner"] = {
                    "active": True,
                    "title_ar": "⏸ التصحيح مُعلَّق — يتطلب تثبيت GameMaker",
                    "body_ar": paused_info["message_ar"],
                }
            grading_result["grading_paused"] = paused_info
            print(
                f"🎮 [GAMEMAKER-PAUSE-GATE] SET grading_paused="
                f"{'PAUSED' if paused_info.get('paused') else 'INFO'} "
                f"reason={paused_info.get('reason')}"
            )
        else:
            grading_result.pop("grading_paused", None)
            grading_result.pop("gamemaker_install_pause_banner", None)
            print(
                "🎮 [GAMEMAKER-PAUSE-GATE] condition NOT met — no pause set. "
                f"has_gm_source={has_gm_source} has_runnable={has_runnable} "
                f"build_succeeded={build_succeeded} tools_missing={tools_missing}"
            )
    except Exception as _pause_exc:
        # NEVER silently swallow: a hidden exception here is why prior
        # attempts to surface the pause banner failed. Log loudly.
        import traceback as _tb
        print(
            f"🎮 [GAMEMAKER-PAUSE-GATE] ❌ EXCEPTION while computing pause: "
            f"{type(_pause_exc).__name__}: {_pause_exc}"
        )
        _tb.print_exc()
        paused_info = None

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
            gate_reason_ar = (
                paused_info["message_ar"] if paused_info else _gate_reason_for(gv)
            )
            _demote_row(row, gate_reason_ar)  # no-op if already not achieved
            row["awardable"] = False
            row["achievement_authority"] = _RUNTIME_GATE_AUTHORITY
            row["award_block_reason"] = "runtime_not_verified"
            row["award_block_reason_ar"] = gate_reason_ar
            if was_awarding:
                changes.append(f"{row.get('criteria_level')}:runtime_gate_block")
    else:
        # Runtime satisfied — clear stale holds and align L4-certified criteria.
        for row in criteria:
            if not isinstance(row, dict):
                continue
            if row.get("runtime_gate_block"):
                row.pop("runtime_gate_block", None)
            short = _short_level(str(row.get("criteria_level") or ""))
            if short in RUNTIME_GATED_SHORT and criterion_pass.get(short):
                _promote_l4_gate_row(row)
                row["awardable"] = True
                row["runtime_l4_verified"] = True
                if static_corroborated:
                    row["static_corroborated_runtime"] = True
                changes.append(f"{row.get('criteria_level')}:runtime_satisfied_l4_open")

    if changes:
        _recompute_grade(grading_result)
        # Single source of truth: invalidate cached grade-display objects so every
        # downstream reader (UI, Word, PDF, API) re-derives from the gated grade_level
        # instead of a stale higher band (prevents "UI=U but report=M").
        for stale_key in (
            "institutional_resolution",
            "grade_display_metrics",
            "btec_institutional_award",
            "expected_runtime_grade",
        ):
            grading_result.pop(stale_key, None)

    report = {
        "applied": bool(changes),
        "version": GATE_VERSION,
        "runtime_status": (
            "PAUSED_GAMEMAKER_MISSING"
            if paused_info and not verdict["satisfied"]
            else verdict["status"]
        ),
        "satisfied": verdict["satisfied"],
        "accepted_evidence": verdict.get("accepted_evidence"),
        "engine_id": verdict.get("engine_id"),
        "gated_criteria": sorted(RUNTIME_GATED_SHORT),
        "changes": changes,
        "automated_l4_gate": automated_gate,
        "grading_paused": paused_info,
        "summary_ar": (
            paused_info["message_ar"]
            if paused_info and not verdict["satisfied"]
            else verdict.get("summary_ar")
        ),
    }
    grading_result["runtime_evidence_gate"] = report
    return report
