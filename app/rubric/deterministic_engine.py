"""

Deterministic Rubric Engine — reproducible rule-based criterion evaluation.



Evidence Registry + execution_mode + INCONCLUSIVE for BASIC runtime gaps.

"""

from __future__ import annotations



import hashlib

import json

import logging

import re

from typing import Any, Dict, List, Optional, Sequence, Tuple



from app.evidence_registry import (

    RUBRIC_RULE_VERSION,

    build_criterion_evidence_registry,

    find_evidence_snippets,

    resolve_execution_mode,

)



logger = logging.getLogger("ai_grader.rubric")



RUBRIC_ENGINE_VERSION = "deterministic_rubric_v2"



_CODE_PATTERN = re.compile(

    r"(?:"
    r"\b(class|def|void|function|using\s+UnityEngine|extends\s+Node|extends\s+CharacterBody2D)\b|"
    r"\b[\w/\\]+\.gd\b|"
    r"\bgdscript\b|"
    r"\bgodot\b|"
    r"\bfunc\s+\w+\s*\("
    r")",

    re.IGNORECASE,

)

_DOC_PATTERN = re.compile(

    r"\b(gdd|design\s+document|peer\s+review|test\s+plan|وثيق|تصميم|مراجعة)\b",

    re.IGNORECASE,

)



_PEER_REVIEW_RULES: Tuple[Tuple[str, re.Pattern], ...] = (

    ("peer_review", re.compile(r"\bpeer\s+review\b", re.I)),

    ("questionnaire", re.compile(r"\bquestionnaire\b", re.I)),

    ("survey", re.compile(r"\bsurvey\b", re.I)),

    ("استبيان", re.compile(r"استبيان")),

    ("نتائج_الاستبيان", re.compile(r"نتائج\s+الاستبيان")),

    ("استطلاع", re.compile(r"استطلاع")),

    ("feedback", re.compile(r"\bfeedback\b", re.I)),

    ("ملاحظات", re.compile(r"ملاحظات")),

)



_TEST_PLAN_RULES: Tuple[Tuple[str, re.Pattern], ...] = (

    ("test_plan", re.compile(r"\btest\s+plan\b", re.I)),

    ("test_case", re.compile(r"\btest\s+case\b", re.I)),

    ("bug_log", re.compile(r"\bbug\s+log\b", re.I)),

    ("خطة_اختبار", re.compile(r"خطة\s+اختبار")),

    ("مرحلة_الاختبار", re.compile(r"مرحلة\s+الاختبار")),

    ("اختبار_وظيف", re.compile(r"اختبار\s+وظيف")),

    ("functional_test", re.compile(r"\bfunctional\s+test\b", re.I)),

    ("testing_phase", re.compile(r"\btesting\s+phase\b", re.I)),

)



_TEST_PLAN_PATTERN = re.compile(

    r"|".join(f"(?:{p.pattern})" for _, p in _TEST_PLAN_RULES),

    re.IGNORECASE,

)

_PEER_REVIEW_PATTERN = re.compile(

    r"|".join(f"(?:{p.pattern})" for _, p in _PEER_REVIEW_RULES),

    re.IGNORECASE,

)



_ANALYSIS_PATTERN = re.compile(

    r"\b(analys|analyze|compare|impact|تحليل|مقارنة|تأثير|سبب|نتيجة)\b",

    re.IGNORECASE,

)

_EVAL_PATTERN = re.compile(

    r"\b(evaluat|recommend|justify|تقييم|توصية|استنتاج|في\s+رأيي)\b",

    re.IGNORECASE,

)





def _normalize_level(level: str) -> str:

    s = (level or "").strip().upper()

    return s.split(".")[-1] if "." in s else s





def _fingerprint(text: str, criteria_levels: Sequence[str]) -> str:

    payload = {"text_len": len(text), "levels": sorted(criteria_levels), "v": RUBRIC_ENGINE_VERSION}

    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]





def _runtime_engine_name(runtime_validation: Optional[Dict[str, Any]]) -> str:

    rv = runtime_validation or {}

    obs = rv.get("observation") or {}

    engine = obs.get("engine") or rv.get("engine")

    if engine:

        return str(engine)

    return "none"





def _smoke_state(runtime_validation: Optional[Dict[str, Any]]) -> Tuple[Optional[bool], bool]:

    smoke = (runtime_validation or {}).get("functional_smoke") or {}

    val = smoke.get("functional_smoke_pass")

    if val is True:

        return True, False

    if val is False:

        return False, False

    reason = str(smoke.get("reason") or "")

    skipped = val is None or reason in ("gated",) or reason.startswith("status_skipped")

    return None, skipped





def _wrap_row(

    *,

    criteria_level: str,

    rule_id: str,

    execution_mode: str,

    runtime: str,

    achieved: bool,

    score: int,

    reason: str,

    authority: str,

    verdict_status: str,

    text: str,

    evidence_rules: Sequence[Tuple[str, re.Pattern]],

    extra_found: Optional[List[Dict[str, str]]] = None,

) -> Dict[str, Any]:

    found, missing = find_evidence_snippets(text, rule_id=rule_id, patterns=evidence_rules)

    if extra_found:

        found = list(extra_found) + found

    result_label = (

        "pass" if achieved else ("inconclusive" if verdict_status == "inconclusive" else "fail")

    )

    from app.rule_bundle import build_decision_provenance_for_execution_mode, copy_provenance

    provenance = build_decision_provenance_for_execution_mode(execution_mode)

    registry = build_criterion_evidence_registry(

        criteria_level=criteria_level,

        rule_id=rule_id,

        result=result_label,

        evidence_found=found,

        evidence_missing=missing if not achieved else [],

        execution_mode=execution_mode,

        reason=reason,

        authority=authority,

        runtime=runtime,

        decision_provenance=provenance,

    )

    return {

        "criteria_level": criteria_level,

        "deterministic_achieved": achieved,

        "deterministic_score": score,

        "reason": reason,

        "authority": authority,

        "verdict_status": verdict_status,

        "rule_id": rule_id,

        "rule_version": provenance.get("rule_version") or RUBRIC_RULE_VERSION,

        "execution_mode": execution_mode,

        "decision_provenance": copy_provenance(provenance),

        "evidence_registry": registry,

    }





def evaluate_criterion_deterministic(

    *,

    criteria_level: str,

    criteria_description: str,

    student_text: str,

    evidence_gate_row: Optional[Dict[str, Any]] = None,

    runtime_validation: Optional[Dict[str, Any]] = None,

    execution_mode: str = "PRO",

) -> Dict[str, Any]:

    short = _normalize_level(criteria_level)

    desc = (criteria_description or "").lower()

    text = student_text or ""

    runtime = _runtime_engine_name(runtime_validation)

    is_basic = execution_mode.upper() == "BASIC"

    smoke_ok, runtime_skipped = _smoke_state(runtime_validation)



    missing = (evidence_gate_row or {}).get("missing_artifacts") or []

    if missing:

        return _wrap_row(

            criteria_level=criteria_level,

            rule_id="evidence_gate",

            execution_mode=execution_mode,

            runtime=runtime,

            achieved=False,

            score=0,

            reason=f"missing_evidence:{','.join(missing)}",

            authority="EVIDENCE_GATE",

            verdict_status="fail",

            text=text,

            evidence_rules=(),

            extra_found=[{"rule_key": "missing", "match": ",".join(missing[:5]), "snippet": ""}],

        )



    # Prototype / playable build criteria — level code only (never match Arabic «إنتاج»
    # in design-criteria descriptions like B.P3/B.P4/B.M2/B.D2).
    if short in ("P5", "C.P5"):

        has_code = bool(_CODE_PATTERN.search(text))

        code_found = (

            [{"rule_key": "code", "match": _CODE_PATTERN.search(text).group(0), "snippet": "source_code"}]

            if has_code

            else []

        )

        if has_code and smoke_ok is True:

            return _wrap_row(

                criteria_level=criteria_level,

                rule_id="code_and_runtime_smoke",

                execution_mode=execution_mode,

                runtime=runtime,

                achieved=True,

                score=75,

                reason="code_present_and_smoke_pass",

                authority="RUNTIME_VALIDATION",

                verdict_status="pass",

                text=text,

                evidence_rules=(),

                extra_found=code_found,

            )

        if has_code and is_basic and (runtime_skipped or smoke_ok is None):

            return _wrap_row(

                criteria_level=criteria_level,

                rule_id="code_runtime_inconclusive",

                execution_mode=execution_mode,

                runtime=runtime,

                achieved=False,

                score=40,

                reason="runtime_not_executed_basic_mode",

                authority="DETERMINISTIC_INCONCLUSIVE",

                verdict_status="inconclusive",

                text=text,

                evidence_rules=(),

                extra_found=code_found,

            )

        if has_code and not is_basic and smoke_ok is not True:

            return _wrap_row(

                criteria_level=criteria_level,

                rule_id="code_deliverable_pro",

                execution_mode=execution_mode,

                runtime=runtime,

                achieved=True,

                score=75,

                reason="code_and_deliverable_report_pro",

                authority="DETERMINISTIC_DOCUMENTARY",

                verdict_status="pass",

                text=text,

                evidence_rules=(),

                extra_found=code_found,

            )

        if has_code:

            return _wrap_row(

                criteria_level=criteria_level,

                rule_id="code_smoke_inconclusive",

                execution_mode=execution_mode,

                runtime=runtime,

                achieved=False,

                score=40,

                reason="code_present_smoke_inconclusive",

                authority="DETERMINISTIC_PARTIAL",

                verdict_status="fail" if smoke_ok is False else "inconclusive",

                text=text,

                evidence_rules=(),

                extra_found=code_found,

            )

        return _wrap_row(

            criteria_level=criteria_level,

            rule_id="no_code_evidence",

            execution_mode=execution_mode,

            runtime=runtime,

            achieved=False,

            score=0,

            reason="no_code_evidence",

            authority="DETERMINISTIC",

            verdict_status="fail",

            text=text,

            evidence_rules=(),

        )



    if short in ("P6", "C.P6") or "test" in desc or "اختبار" in desc:

        from app.pro_evidence_signals import text_has_test_plan_evidence

        has_test_doc = text_has_test_plan_evidence(text)

        if smoke_ok is True and has_test_doc:

            return _wrap_row(

                criteria_level=criteria_level,

                rule_id="functional_smoke_and_test_doc",

                execution_mode=execution_mode,

                runtime=runtime,

                achieved=True,

                score=75,

                reason="functional_smoke_and_test_doc",

                authority="RUNTIME_VALIDATION",

                verdict_status="pass",

                text=text,

                evidence_rules=_TEST_PLAN_RULES,

            )

        if smoke_ok is True:

            return _wrap_row(

                criteria_level=criteria_level,

                rule_id="smoke_no_test_plan",

                execution_mode=execution_mode,

                runtime=runtime,

                achieved=False,

                score=45,

                reason="smoke_pass_no_test_plan",

                authority="DETERMINISTIC",

                verdict_status="fail",

                text=text,

                evidence_rules=_TEST_PLAN_RULES,

            )

        if has_test_doc and is_basic and (runtime_skipped or smoke_ok is None):

            return _wrap_row(

                criteria_level=criteria_level,

                rule_id="test_doc_runtime_inconclusive",

                execution_mode=execution_mode,

                runtime=runtime,

                achieved=False,

                score=35,

                reason="test_doc_basic_no_runtime",

                authority="DETERMINISTIC_INCONCLUSIVE",

                verdict_status="inconclusive",

                text=text,

                evidence_rules=_TEST_PLAN_RULES,

            )

        if has_test_doc and not is_basic:

            return _wrap_row(

                criteria_level=criteria_level,

                rule_id="test_doc_pro_deliverable",

                execution_mode=execution_mode,

                runtime=runtime,

                achieved=True,

                score=75,

                reason="test_plan_documented_pro_mode",

                authority="DETERMINISTIC_DOCUMENTARY",

                verdict_status="pass",

                text=text,

                evidence_rules=_TEST_PLAN_RULES,

            )

        if has_test_doc:

            return _wrap_row(

                criteria_level=criteria_level,

                rule_id="test_doc_only",

                execution_mode=execution_mode,

                runtime=runtime,

                achieved=False,

                score=35,

                reason="test_doc_only_no_runtime",

                authority="DETERMINISTIC",

                verdict_status="fail",

                text=text,

                evidence_rules=_TEST_PLAN_RULES,

            )

        return _wrap_row(

            criteria_level=criteria_level,

            rule_id="no_test_evidence",

            execution_mode=execution_mode,

            runtime=runtime,

            achieved=False,

            score=0,

            reason="no_test_evidence",

            authority="DETERMINISTIC",

            verdict_status="fail",

            text=text,

            evidence_rules=_TEST_PLAN_RULES,

        )



    if short in ("P4", "B.P4", "C.P4") or "peer" in desc or "review" in desc:

        from app.pro_evidence_signals import text_has_design_peer_evidence

        ok = text_has_design_peer_evidence(text)

        return _wrap_row(

            criteria_level=criteria_level,

            rule_id="questionnaire_or_survey",

            execution_mode=execution_mode,

            runtime=runtime,

            achieved=ok,

            score=70 if ok else 0,

            reason="peer_review_evidence" if ok else "peer_review_missing",

            authority="DETERMINISTIC",

            verdict_status="pass" if ok else "fail",

            text=text,

            evidence_rules=_PEER_REVIEW_RULES,

        )



    if short in ("P7", "C.P7") or "present" in desc or "عرض" in desc:

        ok = len(text) > 300 and (

            bool(_DOC_PATTERN.search(text)) or bool(re.search(r"\b(slide|presentation|عرض)\b", text, re.I))

        )

        has_game_ref = bool(_CODE_PATTERN.search(text)) or bool(
            re.search(r"\b(game|لعبة|godot|unity|playtest)\b", text, re.I)
        )

        if ok and smoke_ok is True:

            return _wrap_row(

                criteria_level=criteria_level,

                rule_id="presentation_and_runtime",

                execution_mode=execution_mode,

                runtime=runtime,

                achieved=True,

                score=75,

                reason="presentation_and_runtime_verified",

                authority="RUNTIME_VALIDATION",

                verdict_status="pass",

                text=text,

                evidence_rules=(("presentation", re.compile(r"\b(slide|presentation|عرض)\b", re.I)),),

            )

        if (ok or has_game_ref) and is_basic and (runtime_skipped or smoke_ok is None):

            return _wrap_row(

                criteria_level=criteria_level,

                rule_id="game_presentation_runtime_inconclusive",

                execution_mode=execution_mode,

                runtime=runtime,

                achieved=False,

                score=40,

                reason="game_presentation_basic_no_runtime",

                authority="DETERMINISTIC_INCONCLUSIVE",

                verdict_status="inconclusive",

                text=text,

                evidence_rules=(("presentation", re.compile(r"\b(slide|presentation|عرض)\b", re.I)),),

            )

        return _wrap_row(

            criteria_level=criteria_level,

            rule_id="presentation_evidence",

            execution_mode=execution_mode,

            runtime=runtime,

            achieved=ok,

            score=65 if ok else 0,

            reason="presentation_evidence" if ok else "presentation_insufficient",

            authority="DETERMINISTIC",

            verdict_status="pass" if ok else "fail",

            text=text,

            evidence_rules=(("presentation", re.compile(r"\b(slide|presentation|عرض)\b", re.I)),),

        )



    if short.startswith("M") or short in ("M2", "B.M2", "C.M3", "M3"):

        ok = bool(_ANALYSIS_PATTERN.search(text)) and len(text) > 350

        return _wrap_row(

            criteria_level=criteria_level,

            rule_id="merit_analysis",

            execution_mode=execution_mode,

            runtime=runtime,

            achieved=ok,

            score=70 if ok else 0,

            reason="merit_analysis_present" if ok else "merit_analysis_missing",

            authority="DETERMINISTIC",

            verdict_status="pass" if ok else "fail",

            text=text,

            evidence_rules=(("analysis", _ANALYSIS_PATTERN),),

        )



    if short.startswith("D") or short in ("D2", "BC.D2", "D1"):

        ok = bool(_EVAL_PATTERN.search(text)) and len(text) > 400

        return _wrap_row(

            criteria_level=criteria_level,

            rule_id="distinction_evaluation",

            execution_mode=execution_mode,

            runtime=runtime,

            achieved=ok,

            score=70 if ok else 0,

            reason="distinction_evaluation_present" if ok else "distinction_evaluation_missing",

            authority="DETERMINISTIC",

            verdict_status="pass" if ok else "fail",

            text=text,

            evidence_rules=(("evaluation", _EVAL_PATTERN),),

        )



    if short in ("P3", "B.P3") or "gdd" in desc or "design document" in desc:

        ok = bool(_DOC_PATTERN.search(text)) and len(text) > 400

        return _wrap_row(

            criteria_level=criteria_level,

            rule_id="gdd_document",

            execution_mode=execution_mode,

            runtime=runtime,

            achieved=ok,

            score=70 if ok else 0,

            reason="gdd_text_sufficient" if ok else "gdd_insufficient",

            authority="DETERMINISTIC",

            verdict_status="pass" if ok else "fail",

            text=text,

            evidence_rules=(("gdd", _DOC_PATTERN),),

        )



    return {

        "criteria_level": criteria_level,

        "deterministic_achieved": None,

        "deterministic_score": None,

        "reason": "deferred_to_ai",

        "authority": "NONE",

        "verdict_status": "deferred",

        "rule_id": "deferred",

        "rule_version": RUBRIC_RULE_VERSION,

        "execution_mode": execution_mode,

    }





def merge_deterministic_with_ai(

    grading_result: Dict[str, Any],

    deterministic_rows: List[Dict[str, Any]],

) -> Dict[str, Any]:

    try:

        from app.strict_grading_policy import strict_deterministic_enabled



        strict = strict_deterministic_enabled()

    except Exception:

        strict = True



    by_level = {_normalize_level(r["criteria_level"]): r for r in deterministic_rows}

    criteria = grading_result.get("criteria_results") or []

    changes: List[Dict[str, Any]] = []



    for cr in criteria:

        if not isinstance(cr, dict):

            continue

        det = by_level.get(_normalize_level(str(cr.get("criteria_level") or "")))

        if not det or det.get("deterministic_achieved") is None:

            continue

        ai_was = bool(cr.get("achieved"))

        det_ach = bool(det.get("deterministic_achieved"))

        verdict_status = str(det.get("verdict_status") or ("pass" if det_ach else "fail"))

        cr["deterministic_rubric"] = det

        cr["verdict_status"] = verdict_status

        cr["rule_id"] = det.get("rule_id")

        cr["rule_version"] = det.get("rule_version")

        if det.get("evidence_registry"):

            cr["evidence_registry"] = det["evidence_registry"]

        authority = det.get("authority", "DETERMINISTIC")



        if strict and authority != "NONE":

            if ai_was != det_ach:

                cr["ai_proposed_achieved"] = ai_was

            cr["achieved"] = det_ach

            cr["achievement_authority"] = authority

            cr["score"] = int(det.get("deterministic_score") or (75 if det_ach else 0))

            action = "enforced" if det_ach else (

                "inconclusive" if verdict_status == "inconclusive" else "demoted"

            )

            changes.append({"criteria_level": cr.get("criteria_level"), "action": action})

            continue



        if not det_ach and ai_was:

            cr["achieved"] = False

            cr["ai_proposed_achieved"] = True

            cr["achievement_authority"] = authority

            cr["score"] = min(int(cr.get("score") or 0), int(det.get("deterministic_score") or 0))

            changes.append(

                {

                    "criteria_level": cr.get("criteria_level"),

                    "action": "inconclusive" if verdict_status == "inconclusive" else "demoted",

                }

            )

        elif det_ach and not ai_was and authority == "RUNTIME_VALIDATION":

            cr["deterministic_suggested_achieved"] = True

            changes.append({"criteria_level": cr.get("criteria_level"), "action": "suggested"})



    grading_result["deterministic_rubric_engine"] = {

        "version": RUBRIC_ENGINE_VERSION,

        "rule_version": RUBRIC_RULE_VERSION,

        "execution_mode": grading_result.get("execution_mode"),

        "rows": deterministic_rows,

        "changes": changes,

        "fingerprint": _fingerprint(

            grading_result.get("student_text") or "",

            [r.get("criteria_level", "") for r in criteria if isinstance(r, dict)],

        ),

    }

    logger.info("deterministic_rubric merge changes=%d", len(changes))

    return grading_result





def run_deterministic_rubric(

    grading_result: Dict[str, Any],

    *,

    grading_criteria: Sequence[Dict[str, Any]],

    student_text: str,

    evidence_gate: Optional[Dict[str, Any]] = None,

    runtime_validation: Optional[Dict[str, Any]] = None,

    grading_mode: Optional[str] = None,

) -> Dict[str, Any]:

    mode = resolve_execution_mode(grading_mode or grading_result.get("grading_mode"))

    grading_result["execution_mode"] = mode

    grading_result["grading_mode"] = grading_mode or grading_result.get("grading_mode")



    gate_rows = {

        _normalize_level(r.get("criteria_level", "")): r

        for r in (evidence_gate or {}).get("per_criterion") or []

    }

    rows = []

    for crit in grading_criteria:

        level = str(crit.get("criteria_level") or "")

        rows.append(

            evaluate_criterion_deterministic(

                criteria_level=level,

                criteria_description=str(crit.get("criteria_description") or ""),

                student_text=student_text,

                evidence_gate_row=gate_rows.get(_normalize_level(level)),

                runtime_validation=runtime_validation,

                execution_mode=mode,

            )

        )

    grading_result = merge_deterministic_with_ai(grading_result, rows)

    from app.evidence_registry import attach_evidence_registry_and_metrics



    return attach_evidence_registry_and_metrics(grading_result, grading_mode=grading_mode)


