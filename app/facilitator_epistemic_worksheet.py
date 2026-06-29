"""
Facilitator Epistemic Worksheet — behavioural / linguistic evidence (Section E).

Not a rubric. Not a score. Not a gate.
Produces institutional behavioural evidence for epoch workshop interpretation.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

EPISTEMIC_WORKSHEET_VERSION = "FACILITATOR_EPISTEMIC_WORKSHEET_v1"

CONSTITUTIONAL_PRINCIPLE_AR = (
    "ملاحظة runtime لا تزال ليست سلطة المعيار — "
    "أصبحت أدلة runtime قابلة للملاحظة دون أن تصبح ذاتية التخويل."
)

EPISTEMIC_QUESTIONS: List[Dict[str, str]] = [
    {
        "id": "verification_language_used",
        "question_ar": "هل استخدم المراجع لغة verification؟",
        "reveals_ar": "تضخم السلطة — يبدأ دلالياً",
        "examples_ar": "«واضح أنها شغالة» · «الفيديو يثبت» · «إذن اللعبة مكتملة» · «هذا كافٍ»",
    },
    {
        "id": "replay_before_judgment",
        "question_ar": "هل استُخدم replay قبل الحكم؟",
        "reveals_ar": "ثقة المصدر (provenance)",
        "examples_ar": "فتح Authority Replay قبل أي conclusion",
    },
    {
        "id": "runtime_linked_to_achieved",
        "question_ar": "هل رُبطت runtime observation مباشرة بـ Achieved؟",
        "reveals_ar": "تسرب دلالي — observation → سلطة المعيار",
        "examples_ar": "«إذن C.P5 متحقق» بعد رؤية screenshot أو smoke test",
    },
    {
        "id": "contradictions_remained_visible",
        "question_ar": "هل بقيت contradictions مرئية؟",
        "reveals_ar": "الاحتفاظ بالغموض",
        "examples_ar": "لم يُخفِ downgrade flags أو cross-artifact ambiguity",
    },
    {
        "id": "observation_vs_criterion_distinction",
        "question_ar": "هل فرّق المراجع بين observation وcriterion authority؟",
        "reveals_ar": "فهم الحوكمة — L4 = ملاحظة لا verification",
        "examples_ar": "«observations collected» ≠ «criterion achieved»",
    },
    {
        "id": "modality_dominance_observed",
        "question_ar": "هل ظهرت modality dominance؟",
        "reveals_ar": "سلطة بصرية تتجاوز الأدلة",
        "examples_ar": "«الفيديو يثبت اللعبة» · video overrides contradictions",
    },
    {
        "id": "human_corroboration_requested",
        "question_ar": "هل طلب المراجع human corroboration؟",
        "reveals_ar": "الاحتفاظ بالحوكمة البشرية — مسار L5",
        "examples_ar": "HOLD · طلب مراجعة ثانية · defer until human review",
    },
]

EPISTEMIC_ANSWER_OPTIONS = ("yes", "partial", "no", "not_observed")


def empty_section_e() -> Dict[str, Any]:
    return {
        "answers": {q["id"]: None for q in EPISTEMIC_QUESTIONS},
        "reviewer_language_samples_ar": "",
        "absence_signals_ar": "",
        "facilitator_epistemic_notes_ar": "",
        "authority_boundaries_preserved": None,
    }


def build_section_e_template() -> Dict[str, Any]:
    return {
        "section_version": EPISTEMIC_WORKSHEET_VERSION,
        "constitutional_principle_ar": CONSTITUTIONAL_PRINCIPLE_AR,
        "purpose_ar": (
            "institutional behavioural evidence — "
            "did the reviewer preserve authority boundaries after observing runtime evidence?"
        ),
        "questions": EPISTEMIC_QUESTIONS,
        "answer_options": list(EPISTEMIC_ANSWER_OPTIONS),
        **empty_section_e(),
    }


def normalize_section_e(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    base = empty_section_e()
    if not raw:
        return base
    answers = dict(base["answers"])
    for k, v in (raw.get("answers") or {}).items():
        if k in answers and v in EPISTEMIC_ANSWER_OPTIONS:
            answers[k] = v
    preserved = raw.get("authority_boundaries_preserved")
    if preserved in ("yes", "partial", "no"):
        base["authority_boundaries_preserved"] = preserved
    base["answers"] = answers
    base["reviewer_language_samples_ar"] = str(raw.get("reviewer_language_samples_ar") or "").strip()
    base["absence_signals_ar"] = str(raw.get("absence_signals_ar") or "").strip()
    base["facilitator_epistemic_notes_ar"] = str(raw.get("facilitator_epistemic_notes_ar") or "").strip()
    return base


def _theme_for_answer(qid: str, answer: str) -> Optional[str]:
    if answer in (None, "", "not_observed"):
        return None
    if answer == "yes":
        if qid in (
            "verification_language_used",
            "runtime_linked_to_achieved",
            "modality_dominance_observed",
        ):
            return "semantic_authority_leakage"
        if qid == "observation_vs_criterion_distinction":
            return "governance_understanding_strong"
        if qid == "human_corroboration_requested":
            return "human_governance_retained"
        if qid == "replay_before_judgment":
            return "provenance_consultation"
        if qid == "contradictions_remained_visible":
            return "ambiguity_retained"
    if answer == "no":
        if qid == "observation_vs_criterion_distinction":
            return "governance_boundary_risk"
        if qid == "replay_before_judgment":
            return "provenance_omission"
        if qid == "contradictions_remained_visible":
            return "ambiguity_suppressed"
        if qid in (
            "verification_language_used",
            "runtime_linked_to_achieved",
            "modality_dominance_observed",
        ):
            return "boundary_discipline_observed"
    if answer == "partial":
        return "partial_boundary_retention"
    return None


def synthesize_epistemic_behavioural_evidence(
    observations: List[Dict[str, Any]],
    *,
    batch_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Qualitative institutional behavioural evidence — no score, no gate, no readiness %.
    """
    themes: Dict[str, List[Dict[str, Any]]] = {}
    linguistic_samples: List[Dict[str, Any]] = []
    per_submission: List[Dict[str, Any]] = []

    for obs in observations:
        sid = obs.get("submission_id")
        sec_e = normalize_section_e(obs.get("section_e_epistemic_behaviour"))
        sub_themes: List[str] = []
        for q in EPISTEMIC_QUESTIONS:
            qid = q["id"]
            ans = sec_e["answers"].get(qid)
            theme = _theme_for_answer(qid, ans or "")
            if theme:
                sub_themes.append(theme)
                themes.setdefault(theme, []).append({
                    "submission_id": sid,
                    "question_id": qid,
                    "answer": ans,
                    "question_ar": q["question_ar"],
                })
        if sec_e.get("reviewer_language_samples_ar"):
            linguistic_samples.append({
                "submission_id": sid,
                "samples_ar": sec_e["reviewer_language_samples_ar"],
            })
        absence = sec_e.get("absence_signals_ar") or ""
        if absence:
            themes.setdefault("absence_signals", []).append({
                "submission_id": sid,
                "absence_signals_ar": absence,
            })
        if any(v for v in sec_e["answers"].values()):
            per_submission.append({
                "submission_id": sid,
                "authority_boundaries_preserved": sec_e.get("authority_boundaries_preserved"),
                "themes": sorted(set(sub_themes)),
                "facilitator_notes_excerpt": (sec_e.get("facilitator_epistemic_notes_ar") or "")[:200],
            })

    leakage = themes.get("semantic_authority_leakage", [])
    boundary_risk = themes.get("governance_boundary_risk", [])
    provenance_omit = themes.get("provenance_omission", [])

    facilitator_interpretation: List[str] = []
    if linguistic_samples:
        facilitator_interpretation.append(
            f"وُثّقت {len(linguistic_samples)} عينة لغوية — راجع wording discipline في الورشة."
        )
    if leakage:
        facilitator_interpretation.append(
            "semantic authority leakage observed — authority inflation may start linguistically."
        )
    if boundary_risk:
        facilitator_interpretation.append(
            "reviewers may not distinguish observation vs criterion authority — L4 workshop focus."
        )
    if provenance_omit:
        facilitator_interpretation.append(
            "replay not consistently consulted before judgment — provenance trust at risk."
        )
    absence_entries = themes.get("absence_signals", [])
    if absence_entries:
        facilitator_interpretation.append(
            f"وُثّقت {len(absence_entries)} حالة absence — "
            "contradiction غير مذكورة · replay متأخر · uncertainty اختفت · corroboration لم تُطلب."
        )
    if not observations:
        facilitator_interpretation.append(
            "لا observations بعد — Section E epistemic worksheet مطلوب قبل epoch signing."
        )
    elif not leakage and not boundary_risk and len(observations) >= 3:
        facilitator_interpretation.append(
            "early signal: reviewers may resist turning runtime observation into verification authority."
        )

    result = {
        "report_type": "institutional_behavioural_evidence",
        "not": "score · gate · readiness percentage",
        "section_version": EPISTEMIC_WORKSHEET_VERSION,
        "batch_id": batch_id,
        "constitutional_principle_ar": CONSTITUTIONAL_PRINCIPLE_AR,
        "core_question_ar": (
            "did the reviewer preserve authority boundaries "
            "after observing runtime evidence?"
        ),
        "observations_with_section_e": len(per_submission),
        "total_observations": len(observations),
        "behavioural_themes": {
            theme: entries for theme, entries in sorted(themes.items())
        },
        "linguistic_leakage_examples": linguistic_samples,
        "absence_signal_records": themes.get("absence_signals", []),
        "implicit_legitimacy_watch_ar": (
            "كيف استقرّت اليقين نفسياً بعد أن أصبح runtime evidence observable — "
            "حتى بدون تغيير رسمي في authority"
        ),
        "per_submission_summary": per_submission,
        "facilitator_interpretation_ar": facilitator_interpretation,
        "workshop_focus_ar": [
            "how reviewers talk after seeing runtime evidence",
            "wording discipline — not telemetry richness",
            "reviewer epistemic behaviour under runtime ambiguity",
        ],
        "explicitly_not_for": [
            "automatic institutional veto",
            "L4 sandbox enablement",
            "epoch transition gate",
        ],
    }

    from app.epistemic_leakage_lexicon import enrich_epistemic_synthesis

    return enrich_epistemic_synthesis(result, observations=observations)
