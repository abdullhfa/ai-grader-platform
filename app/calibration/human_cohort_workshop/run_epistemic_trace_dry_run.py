"""
Deliberate epistemic trace dry-run — architecture verification only.

Does NOT append to observations.jsonl (cohort integrity).
Writes trace to epistemic_trace_captures.jsonl + dry-run report artifact.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.epistemic_trace_capture import (
    append_epistemic_trace,
    enrich_trace_advisory,
    normalize_epistemic_trace,
)

WORKSHOP = Path(__file__).resolve().parent
DRY_RUN_ID = "epistemic_trace_dry_run_submission_6_v1"
SUBMISSION_ID = 6
BATCH_ID = 4

# Deliberate chronology: replay consult BEFORE authority vocabulary escalation
REPLAY_OPENED = "2026-05-20T14:00:00Z"
REPLAY_CONSULTED = "2026-05-20T14:08:00Z"
AUTHORITY_LANGUAGE = "2026-05-20T14:35:00Z"


def build_ui_payload() -> dict:
    """Mirrors governance_pilot_observatory.html buildEpistemicTrace() + form context."""
    return {
        "replay_chronology": {
            "replay_opened_at": REPLAY_OPENED,
            "replay_consulted_at": REPLAY_CONSULTED,
            "authority_language_first_seen_at": AUTHORITY_LANGUAGE,
            "replay_precedes_authority": None,
        },
        "authority_formation_markers": {
            "verification_lexicon_detected": "yes",
            "closure_trigger_detected": (
                "جودة السرد النظري + Pass/Merit language رغم L0 — "
                "representation completeness (partial #3 pattern, no GDD collapse)"
            ),
            "temptation_classification": "representational",
            "authority_formation_altered": "yes",
        },
        "quarantine_state_capture": {
            "quarantine_state": "maintained",
            "qb_level": "QB3",
            "quarantine_breach_reason": "",
            "restraint_anchor_detected": (
                "L0 runtime_evidence_level · absent exe · HOLD applied — "
                "quarantine descriptive not normative pass/fail"
            ),
        },
        "provenance_continuity": {
            "exe_present": False,
            "exe_identity_matches_submission": False,
            "runtime_corroborated": False,
            "provenance_continuity_state": "broken",
        },
        "counterfactual_capture": {
            "counterfactual_without_replay": (
                "بدون replay كان سيُغلق على Pass/Merit بناءً على جودة التحليل النصي "
                "دون رؤية L0 و screenshot_count=0 — legitimacy by narrative adequacy"
            ),
            "intuition_closure_detected": "yes",
            "replay_changed_outcome": "yes",
        },
    }


def build_observation_shell(trace_raw: dict) -> dict:
    """Minimal observation record for advisory enrichment — not saved to observations.jsonl."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    return {
        "dry_run_id": DRY_RUN_ID,
        "observation_kind": "epistemic_trace_architecture_dry_run",
        "excluded_from_cohort_metrics": True,
        "submission_id": SUBMISSION_ID,
        "batch_id": BATCH_ID,
        "logged_at": now,
        "replay_consulted_at": REPLAY_CONSULTED,
        "section_a_runtime_evidence_state": {
            "executable_detected": False,
            "runtime_evidence_level": "L0",
            "replay_available": True,
        },
        "section_b_reviewer_behaviour": {
            "l3_interpreted_as_verification": True,
            "replay_opened": True,
            "authority_boundary_overridden": True,
            "hold_applied": True,
        },
        "section_e_epistemic_behaviour": {
            "answers": {
                "verification_language_used": "yes",
                "replay_before_judgment": "partial",
                "runtime_linked_to_achieved": "yes",
            },
            "reviewer_language_samples_ar": (
                '"قدم الطالب وثيقة تصميم مفصلة للغاية"\n'
                '"قدم تقييمًا نقديًا شاملًا"'
            ),
        },
        "section_f_epistemic_trace": trace_raw,
        "profile_ar": (
            "submission #6 — representational → authority drift "
            "(partial #3 pattern, NOT #3/#13 — no exe stress)"
        ),
    }


def verify_checks(trace: dict, ui_payload: dict) -> list[dict]:
    """Five deliberate architecture checks from dry-run spec."""
    chrono = trace["replay_chronology"]
    checks = []

    ui_groups = set(ui_payload.keys())
    trace_groups = {
        k for k in trace.keys()
        if k in ui_groups and isinstance(trace[k], dict)
    }
    field_ok = ui_groups == trace_groups and all(
        set(ui_payload[g].keys()) <= set(trace[g].keys())
        for g in ui_groups
    )
    checks.append({
        "check_id": "trace_integrity",
        "question_ar": "هل تنتقل الحقول كاملة من UI → ledger؟",
        "pass": field_ok and trace.get("schema_id") == "EPISTEMIC_TRACE_CAPTURE_SCHEMA_v1",
        "detail_ar": (
            f"groups preserved: {field_ok}; "
            f"replay_precedes_authority computed={chrono.get('replay_precedes_authority')}"
        ),
    })

    t_open = chrono.get("replay_opened_at")
    t_consult = chrono.get("replay_consulted_at")
    t_auth = chrono.get("authority_language_first_seen_at")
    timing_ok = (
        t_open < t_consult < t_auth
        and chrono.get("replay_precedes_authority") is True
    )
    checks.append({
        "check_id": "timing_fidelity",
        "question_ar": "هل replay timestamps تحفظ التسلسل الحقيقي؟",
        "pass": timing_ok,
        "detail_ar": f"{t_open} < {t_consult} < {t_auth}",
    })

    qsc = trace["quarantine_state_capture"]
    quarantine_ok = (
        qsc.get("quarantine_state") in ("active", "maintained", "breached", "lifted")
        and qsc.get("qb_level") == "QB3"
        and "advisory_enrichment" in trace
        and trace["advisory_enrichment"].get("wire_to_grading") is False
    )
    checks.append({
        "check_id": "quarantine_persistence",
        "question_ar": "هل يبقى state منفصلًا عن الحكم؟",
        "pass": quarantine_ok,
        "detail_ar": (
            f"facilitator quarantine_state={qsc.get('quarantine_state')}; "
            "wire_to_grading=False"
        ),
    })

    lex = trace["authority_formation_markers"].get("verification_lexicon_detected")
    checks.append({
        "check_id": "vocabulary_capture",
        "question_ar": "هل يتم رصد authority lexicon تلقائيًا؟",
        "pass": lex == "yes",
        "auto_detected": False,
        "detail_ar": (
            "facilitator manual select — no auto-detection from language samples yet; "
            "value preserved in ledger when set"
        ),
    })

    cf = trace["counterfactual_capture"].get("counterfactual_without_replay", "")
    cf_ok = len(cf) > 40 and trace["counterfactual_capture"].get("replay_changed_outcome") == "yes"
    checks.append({
        "check_id": "counterfactual_usefulness",
        "question_ar": 'هل حقل "without replay" يعطي insight حقيقي؟',
        "pass": cf_ok,
        "detail_ar": cf[:120] + "…",
    })

    return checks


def main() -> dict:
    ui_payload = build_ui_payload()
    record = build_observation_shell(ui_payload)
    trace = normalize_epistemic_trace(
        ui_payload,
        section_a=record["section_a_runtime_evidence_state"],
        replay_consulted_at=record["replay_consulted_at"],
    )
    enrich_trace_advisory(trace, record)
    record["section_f_epistemic_trace"] = trace

    trace_id = append_epistemic_trace(record)
    checks = verify_checks(trace, ui_payload)
    all_pass = all(c["pass"] for c in checks)

    report = {
        "dry_run_id": DRY_RUN_ID,
        "title": "Epistemic trace architecture dry-run",
        "submission_id": SUBMISSION_ID,
        "batch_id": BATCH_ID,
        "profile_ar": record["profile_ar"],
        "why_submission_6_ar": (
            "مشابه جزئيًا لـ #3 (representation → authority) لكن ليس #3 ولا #13 — "
            "L0 بدون exe · اختبار drift مبكر + replay timing قبل vocabulary escalation"
        ),
        "trace_id": trace_id,
        "ledger_path": "app/calibration/human_cohort_workshop/epistemic_trace_captures.jsonl",
        "observations_jsonl_appended": False,
        "architecture_checks": checks,
        "all_checks_pass": all_pass,
        "observer_role_drift_check_ref": "OBSERVER_ROLE_DRIFT_CHECK_v1.json",
        "ui_invariant": (
            "This interface records epistemic state transitions. "
            "It does not assign authority."
        ),
        "section_f_epistemic_trace": trace,
    }

    out_path = WORKSHOP / "epistemic_trace_dry_run_submission_6.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    r = main()
    print(json.dumps({
        "dry_run_id": r["dry_run_id"],
        "trace_id": r["trace_id"],
        "all_checks_pass": r["all_checks_pass"],
        "checks": [{c["check_id"]: c["pass"]} for c in r["architecture_checks"]],
    }, ensure_ascii=False, indent=2))
