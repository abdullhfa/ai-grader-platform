"""
Runtime-to-criterion mapping — advisory + deterministic adjudication for execution criteria.

mapped evidence ≠ automatic achievement unless operational floor satisfied.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

MAPPING_ID = "RUNTIME_CRITERION_MAPPING_v1"

EXECUTION_CRITERIA = frozenset({"C.P5", "C.P6"})


def _has_executable_artifacts(inv: Dict[str, Any]) -> bool:
    exe = inv.get("executable_artifacts") or {}
    rt = inv.get("runtime_artifacts") or {}
    return bool(exe.get("files") or rt.get("executables_detected"))


def observation_allows_adjudication(
    observation: Optional[Dict[str, Any]],
    inventory: Optional[Dict[str, Any]] = None,
) -> bool:
    """L4 completed OR L5 manual playtest under GOVERNANCE_FREEZE (gated + exe + human verified)."""
    obs = observation or {}
    inv = inventory or {}
    if obs.get("status") == "completed":
        return True
    human = bool(
        obs.get("human_playtest_verified")
        or obs.get("manual_playtest_verified")
        or obs.get("interaction_visually_corroborated")
    )
    return obs.get("status") == "gated" and human and _has_executable_artifacts(inv)


def _short_level(level: str) -> str:
    lv = (level or "").strip()
    return lv.split(".")[-1].upper() if "." in lv else lv.upper()


def is_execution_criterion(criteria_level: str) -> bool:
    full = (criteria_level or "").strip().upper()
    short = _short_level(full)
    return full in EXECUTION_CRITERIA or short in {"P5", "P6"}


def evaluate_operational_support(
    observation: Optional[Dict[str, Any]],
    inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Per-criterion operational support from runtime observation."""
    inv = inventory or {}
    obs = observation or {}
    graph = obs.get("runtime_signal_graph") or {}
    signals = graph.get("signals") or {}
    analyses = obs.get("artifact_analyses") or []

    apk_ok = any(a.get("type") == "apk" and a.get("valid") for a in analyses)
    pck_ok = any(a.get("type") == "pck" and a.get("valid") for a in analyses)
    smoke_ok = any(
        a.get("smoke_result") in ("stable_window", "launch_ok") for a in analyses
    )
    smoke_partial = any(a.get("smoke_result") == "launch_ok" for a in analyses)
    unity_observed = any(a.get("engine") == "unity" for a in analyses)
    interaction_trace = any(
        signals.get(k) in ("detected", "yes", "observed")
        for k in ("player_moved", "score_changed", "collision_events", "level_transition")
    )
    automated_interaction = signals.get("automated_interaction_observed") == "yes"
    human_playtest = bool(
        obs.get("human_playtest_verified")
        or obs.get("manual_playtest_verified")
        or obs.get("interaction_visually_corroborated")
    )
    smoke_only = smoke_ok and not (apk_ok or pck_ok or interaction_trace or human_playtest)
    crash = signals.get("crash") == "observed" and not smoke_ok and not smoke_partial
    testing_doc = (inv.get("testing_evidence") or {}).get("status") in (
        "partial",
        "documented",
        "analyzed",
    )
    has_doc = bool((inv.get("documentation") or {}).get("files"))
    godot = (inv.get("runtime_artifacts") or {}).get("godot_export_detected")

    gameplay_sem = {}
    try:
        from app.gameplay_semantic_verification import assess_gameplay_semantics

        gameplay_sem = assess_gameplay_semantics(obs, inventory=inv)
    except Exception:
        gameplay_sem = {}

    cp5_score = 0
    cp5_reasons: List[str] = []
    if pck_ok:
        cp5_score += 35
        cp5_reasons.append("Godot PCK صالح — scenes/assets مُرصدة")
    if apk_ok:
        cp5_score += 30
        cp5_reasons.append("APK structure صالح (dex+manifest)")
    if smoke_ok:
        if smoke_only:
            cp5_score += 18
            cp5_reasons.append("EXE launch/smoke فقط — gameplay غير مُتحقَّق")
        else:
            cp5_score += 35
            cp5_reasons.append("EXE smoke/launch observation مع corroboration إضافية")
    elif smoke_partial and apk_ok and pck_ok:
        cp5_score += 25
        cp5_reasons.append("EXE launch attempt + APK/PCK corroboration")
    if godot:
        cp5_score += 10
        cp5_reasons.append("Godot export detected")
    if crash and not smoke_ok:
        cp5_score = min(cp5_score, 25)
        cp5_reasons.append("crash/early exit observed")
    if unity_observed:
        cp5_reasons.append("Unity L4 observation استشارية — تتطلب playtest بشري للـ Achieved")
    if gameplay_sem.get("interaction_detected"):
        cp5_score += 8
        cp5_reasons.append("interaction_detected during gameplay session")
    if gameplay_sem.get("progression_detected"):
        cp5_score += 12
        cp5_reasons.append("level progression / checkpoint observed")
    if gameplay_sem.get("fail_state_detected"):
        cp5_score += 10
        cp5_reasons.append("fail-state path observed (game over/death)")
    if gameplay_sem.get("gameplay_loop_complete"):
        cp5_score += 14
        cp5_reasons.append("gameplay loop complete (menu/gameplay/fail|win flow)")
    if gameplay_sem.get("progression_missing"):
        cp5_score = min(cp5_score, 52)
        cp5_reasons.append("progression_missing — gameplay transition غير مثبت")
    if gameplay_sem.get("loop_incomplete"):
        cp5_score = min(cp5_score, 48)
        cp5_reasons.append("gameplay_loop_incomplete — التحقق المؤسسي غير مكتمل")

    cp6_score = cp5_score // 2
    cp6_reasons = list(cp5_reasons)
    if automated_interaction:
        cp6_reasons.append(
            "automated interaction trace — HOLD حتى playtest بشري"
        )
        cp5_reasons.append(
            "تفاعل آلي L5 مُرصد — visual delta استشاري ولا يكفي لـ Achieved"
        )
    if testing_doc or has_doc:
        cp6_score += 25
        cp6_reasons.append("testing documentation present")
    if gameplay_sem.get("progression_detected"):
        cp6_score += 15
        cp6_reasons.append("progression checkpoint observed")
    if gameplay_sem.get("fail_state_detected"):
        cp6_score += 12
        cp6_reasons.append("fail-state logic observed")
    if gameplay_sem.get("lives_or_health_detected"):
        cp6_score += 8
        cp6_reasons.append("lives/health system observed")
    if gameplay_sem.get("restart_flow_detected") or gameplay_sem.get("menu_navigation_detected"):
        cp6_score += 10
        cp6_reasons.append("restart/menu navigation flow observed")
    if gameplay_sem.get("gameplay_loop_complete"):
        cp6_score += 12
        cp6_reasons.append("gameplay loop completed")
    if gameplay_sem.get("progression_missing"):
        cp6_score = min(cp6_score, 50)
        cp6_reasons.append("no clear level transition — examiner verification required")
    if gameplay_sem.get("loop_incomplete"):
        cp6_score = min(cp6_score, 46)
        cp6_reasons.append("gameplay loop incomplete")

    # L5-only path when L4 sandbox is gated (GOVERNANCE_FREEZE_v1)
    has_exe = bool((inv.get("executable_artifacts") or {}).get("files"))
    l5_freeze_path = (
        human_playtest
        and has_exe
        and obs.get("status") == "gated"
        and not smoke_ok
    )
    if l5_freeze_path:
        cp5_score = max(cp5_score, 78)
        cp6_score = max(cp6_score, 72)
        cp5_reasons.append(
            "Manual Playtest L5 — teacher verified gameplay (GOVERNANCE_FREEZE path)"
        )
        cp6_reasons.append("L5 operational verification — لا L4 sandbox")

    if smoke_ok and not smoke_only:
        cp6_score += 20
        cp6_reasons.append("runnable artifact smoke-stable")
    elif smoke_only:
        cp6_score += 8
        cp6_reasons.append("smoke-only لا يكفي لإثبات الاختبار أو التشغيل التعليمي")

    def _verdict(score: int, crash_flag: bool) -> str:
        if crash_flag and not smoke_ok:
            return "insufficient"
        if score >= 70:
            return "operational_support_strong"
        if score >= 45:
            return "operational_support_partial"
        return "insufficient"

    cp5_verdict = _verdict(cp5_score, crash)
    cp6_verdict = _verdict(cp6_score, crash)
    if l5_freeze_path:
        cp5_verdict = "operational_support_strong"
        cp6_verdict = "operational_support_strong"
    if smoke_only and not l5_freeze_path:
        if cp5_verdict == "operational_support_strong":
            cp5_verdict = "operational_support_partial"
        if cp6_verdict == "operational_support_strong":
            cp6_verdict = "operational_support_partial"

    l5_verified_support = bool(
        gameplay_sem.get("gameplay_loop_complete")
        and gameplay_sem.get("progression_detected")
        and gameplay_sem.get("fail_state_detected")
    )
    cp5_suggested = bool(
        (
            cp5_verdict == "operational_support_strong"
            and (interaction_trace or human_playtest or gameplay_sem.get("interaction_detected"))
            and not smoke_only
            and not gameplay_sem.get("progression_missing")
            and not gameplay_sem.get("loop_incomplete")
        )
        or l5_verified_support
    )
    cp6_suggested = bool(
        (
            cp6_verdict == "operational_support_strong"
            and (interaction_trace or human_playtest or gameplay_sem.get("interaction_detected"))
            and not smoke_only
            and not gameplay_sem.get("progression_missing")
            and not gameplay_sem.get("loop_incomplete")
        )
        or l5_verified_support
    )

    return {
        "mapping_id": MAPPING_ID,
        "C.P5": {
            "support_level": cp5_verdict,
            "support_score": min(100, cp5_score),
            "reasons_ar": cp5_reasons,
            "suggested_achieved": cp5_suggested,
            "needs_human_playtest": not cp5_suggested,
            "smoke_only": smoke_only,
        },
        "C.P6": {
            "support_level": cp6_verdict,
            "support_score": min(100, cp6_score),
            "reasons_ar": cp6_reasons,
            "suggested_achieved": cp6_suggested,
            "needs_human_playtest": not cp6_suggested,
            "smoke_only": smoke_only,
        },
        "runtime_verified": bool(obs.get("runtime_verified")),
        "runtime_observed": bool(obs.get("runtime_observed")),
        "automated_interaction_observed": automated_interaction,
        "visual_response_to_input": signals.get("visual_response_to_input", "none"),
        "gameplay_semantic": gameplay_sem,
        "l5_verified_support": l5_verified_support,
        "note_ar": (
            "mapped evidence ≠ automatic achievement — smoke-only أو automated interaction يبقى HOLD/مراجعة بشرية."
        ),
    }


def _build_runtime_note_ar(level: str, sup: Dict[str, Any], *, outcome: str) -> str:
    """Human-readable Arabic runtime note (stored separately from AI feedback)."""
    verdict = sup.get("support_level", "insufficient")
    verdict_key = str(verdict).replace("_", " ")
    reasons = sup.get("reasons_ar") or []
    fake_block = (
        f"✅ [Runtime observation L4] {level}: {verdict_key} — "
        + "; ".join(reasons)
        + ". Observations collected under controlled conditions."
    )
    if outcome == "not_achieved":
        fake_block = (
            f"❌ [Runtime adjudication] {level}: insufficient — "
            + "; ".join(reasons)
        )
    elif outcome == "human_review":
        fake_block = f"⏸ [Runtime partial] {level}: corroboration partial — verifier review."
    from app.report_feedback_formatter import format_runtime_section
    return format_runtime_section(fake_block)


def apply_runtime_criterion_adjudication(
    grading_result: Dict[str, Any],
    *,
    observation: Optional[Dict[str, Any]] = None,
    inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Deterministic layer for C.P5/C.P6 after AI grading.
    - Strong operational support + interaction/human corroboration → allow Achieved
    - Smoke-only launch → HOLD / human review, never automatic Achieved
    - Insufficient + AI achieved → block (via achievement_authority)
    - Insufficient + AI not achieved → keep Not Achieved
    - Crash → Not Achieved
    """
    inv = inventory or grading_result.get("artifact_inventory") or {}
    obs = observation or inv.get("runtime_observation_report") or {}
    if not observation_allows_adjudication(obs, inv):
        return {"applied": False, "reason": "no_observation"}

    support = evaluate_operational_support(obs, inv)
    analyses = obs.get("artifact_analyses") or []
    pck_ok = any(a.get("type") == "pck" and a.get("valid") for a in analyses)
    apk_ok = any(a.get("type") == "apk" and a.get("valid") for a in analyses)
    testing_doc = (inv.get("testing_evidence") or {}).get("status") in (
        "partial",
        "documented",
        "analyzed",
    )
    human_playtest = bool(
        obs.get("human_playtest_verified")
        or obs.get("manual_playtest_verified")
        or obs.get("interaction_visually_corroborated")
    )
    criteria = grading_result.get("criteria_results") or []
    changes: List[Dict[str, Any]] = []

    for cr in criteria:
        if not isinstance(cr, dict):
            continue
        level = str(cr.get("criteria_level") or "")
        if not is_execution_criterion(level):
            continue
        key = level.upper() if level.upper() in support else (
            "C.P5" if _short_level(level) == "P5" else "C.P6"
        )
        sup = support.get(key) or {}
        verdict = sup.get("support_level", "insufficient")
        suggested = bool(sup.get("suggested_achieved"))
        ai_was = bool(cr.get("achieved"))

        if verdict == "insufficient":
            det = cr.get("deterministic_rubric") or {}
            if bool(det.get("deterministic_achieved")) or str(cr.get("verdict_status") or "").lower() == "pass":
                cr["runtime_observation_note_ar"] = _build_runtime_note_ar(
                    level, sup, outcome="human_review"
                )
                changes.append({"criteria_level": level, "action": "defer_deterministic_pass"})
                continue
            if ai_was:
                cr["ai_proposed_achieved"] = True
            # Documentary + shipped game (PCK/APK/EXE) — defer to criteria finalizer; avoid hard 0/score lock
            short = _short_level(level)
            doc_path = bool(
                (inv.get("documentation") or {}).get("files")
                or inv.get("has_source_code_artifacts")
            )
            shipped = bool((inv.get("executable_artifacts") or {}).get("files")) or bool(
                inv.get("has_executable_artifacts")
            )
            if short == "P6" and (testing_doc or doc_path) and shipped and ai_was:
                cr["achievement_authority"] = "RUNTIME_DEFER_DELIVERABLE"
                cr["runtime_observation_note_ar"] = _build_runtime_note_ar(
                    level, sup, outcome="human_review"
                )
                changes.append({"criteria_level": level, "action": "defer_deliverable_p6"})
                continue
            if short == "P5" and (pck_ok or apk_ok) and shipped and ai_was:
                cr["achievement_authority"] = "RUNTIME_DEFER_DELIVERABLE"
                cr["runtime_observation_note_ar"] = _build_runtime_note_ar(
                    level, sup, outcome="human_review"
                )
                changes.append({"criteria_level": level, "action": "defer_deliverable_p5"})
                continue
            cr["achieved"] = False
            cr["achievement_authority"] = (
                "RUNTIME_INSUFFICIENT" if verdict == "insufficient" else "HUMAN_REVIEW_REQUIRED"
            )
            cr["runtime_observation_note_ar"] = _build_runtime_note_ar(
                level, sup, outcome="not_achieved"
            )
            changes.append({"criteria_level": level, "action": "not_achieved_insufficient"})
        elif suggested:
            cr["achieved"] = True
            cr["achievement_authority"] = (
                "HUMAN_PLAYTEST_L5" if human_playtest else "RUNTIME_OBSERVATION_L4"
            )
            cr["runtime_observation_note_ar"] = _build_runtime_note_ar(
                level, sup, outcome="achieved"
            )
            changes.append({
                "criteria_level": level,
                "action": "achieved_l5_human" if human_playtest else "achieved_l4_support",
            })
        else:
            # partial — human review
            cr["achieved"] = False
            cr["achievement_authority"] = "HUMAN_REVIEW_REQUIRED"
            cr["runtime_observation_note_ar"] = _build_runtime_note_ar(
                level, sup, outcome="human_review"
            )
            changes.append({"criteria_level": level, "action": "human_review_partial"})

    grading_result["runtime_criterion_mapping"] = support
    grading_result["runtime_adjudication"] = {
        "mapping_id": MAPPING_ID,
        "changes": changes,
        "observation_level": obs.get("runtime_evidence_level"),
    }

    if changes:
        from app.btec_grade_resolution import determine_grade_level

        grading_result["criteria_results"] = criteria
        new_grade = determine_grade_level(criteria)
        grading_result["grade_level"] = new_grade
        total_score_sum = sum(int(c.get("score") or 0) for c in criteria)
        total_count = len(criteria) or 1
        pct = int(total_score_sum / total_count)
        grading_result["percentage"] = pct
        grading_result["total_score"] = pct

    return {"applied": True, "changes": changes, "support": support}
