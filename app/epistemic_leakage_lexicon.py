"""
Epistemic Leakage Lexicon — institutional semantic drift vocabulary.

Advisory pattern recognition on facilitator language samples only.
Not a score. Not a gate. Not automated governance classification.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

LEXICON_VERSION = "EPISTEMIC_LEAKAGE_LEXICON_v1"

# leakage_type → institutional meaning (not severity score)
LEAKAGE_TYPES: Dict[str, str] = {
    "implicit_runtime_verification": "runtime observation treated as verification",
    "modality_dominance": "visual/video modality elevated to proof",
    "criterion_escalation": "observation language escalated to criterion authority",
    "runtime_authority_collapse": "launch/observability collapsed into correctness",
    "provenance_overreach": "replay or provenance treated as sufficient verification",
    "narrative_first_confirmation": "verbal impression confirmed by evidence post-hoc",
    "contradiction_suppression": "ambiguity or downgrade hidden after observability",
}

LEXICON_ENTRIES: List[Dict[str, Any]] = [
    {
        "entry_id": "ELL_001",
        "phrase_ar": "واضح أنها شغالة",
        "phrase_en": "clearly it works",
        "leakage_type": "implicit_runtime_verification",
        "interpretation_ar": "implicit runtime verification — observability → certainty",
        "constitutional_violation_ar": "runtime observation is still not criterion authority",
        "facilitator_prompt_ar": "هل قالها قبل replay؟ هل contradictions ظهرت؟",
    },
    {
        "entry_id": "ELL_002",
        "phrase_ar": "الفيديو يثبت",
        "phrase_en": "the video proves",
        "leakage_type": "modality_dominance",
        "interpretation_ar": "modality dominance — video as proof not hint",
        "constitutional_violation_ar": "video raises plausibility, not authority",
        "facilitator_prompt_ar": "هل contradictions بقيت مرئية بعد الفيديو؟",
    },
    {
        "entry_id": "ELL_003",
        "phrase_ar": "إذن C.P5 متحقق",
        "phrase_en": "therefore C.P5 is achieved",
        "leakage_type": "criterion_escalation",
        "interpretation_ar": "criterion escalation — observation → Achieved wire",
        "constitutional_violation_ar": "mapped evidence ≠ automatic achievement",
        "facilitator_prompt_ar": "هل فرّق بين observation وcriterion authority؟",
    },
    {
        "entry_id": "ELL_004",
        "phrase_ar": "ما دام اشتغلت فهي صحيحة",
        "phrase_en": "since it ran it is correct",
        "leakage_type": "runtime_authority_collapse",
        "interpretation_ar": "runtime-authority collapse — launch = correctness",
        "constitutional_violation_ar": "presence ≠ achievement",
        "facilitator_prompt_ar": "هل smoke/launch رُبط بـ grading outcome؟",
    },
    {
        "entry_id": "ELL_005",
        "phrase_ar": "الـ replay كافي",
        "phrase_en": "replay is enough",
        "leakage_type": "provenance_overreach",
        "interpretation_ar": "provenance overreach — replay absolutized",
        "constitutional_violation_ar": "replay supports judgement — does not replace human authority",
        "facilitator_prompt_ar": "هل replay استُخدم كـ verification أم كـ provenance consult؟",
    },
    {
        "entry_id": "ELL_006",
        "phrase_ar": "اللعبة صحيحة",
        "phrase_en": "the game is correct",
        "leakage_type": "implicit_runtime_verification",
        "interpretation_ar": "game correctness claim from partial evidence",
        "constitutional_violation_ar": "forbidden: game verified / game works",
        "facilitator_prompt_ar": "هل اللغة institutional contract compliant؟",
    },
    {
        "entry_id": "ELL_007",
        "phrase_ar": "game verified",
        "phrase_en": "game verified",
        "leakage_type": "implicit_runtime_verification",
        "interpretation_ar": "explicit forbidden verification language",
        "constitutional_violation_ar": "GOVERNANCE_FREEZE forbidden claim",
        "facilitator_prompt_ar": "document as GFM_AUTHORITY_INFLATION if repeated",
    },
    {
        "entry_id": "ELL_008",
        "phrase_ar": "بما أننا شفناها",
        "phrase_en": "since we saw it",
        "leakage_type": "narrative_first_confirmation",
        "interpretation_ar": "narrative-first authority — impression before provenance",
        "constitutional_violation_ar": "Authority Replay first — before verbal interpretation",
        "facilitator_prompt_ar": "هل replay فُتح قبل هذه العبارة؟",
    },
    {
        "entry_id": "ELL_009",
        "phrase_ar": "ما في تناقض",
        "phrase_en": "no contradiction",
        "leakage_type": "contradiction_suppression",
        "interpretation_ar": "contradiction suppression after observability",
        "constitutional_violation_ar": "contradictions downgrade authority — not invisible",
        "facilitator_prompt_ar": "هل flags كانت موجودة في replay؟",
    },
    {
        "entry_id": "ELL_010",
        "phrase_ar": "الـ telemetry يثبت",
        "phrase_en": "telemetry proves",
        "leakage_type": "criterion_escalation",
        "interpretation_ar": "telemetry interpreted as verification",
        "constitutional_violation_ar": "telemetry timeline is advisory",
        "facilitator_prompt_ar": "هل telemetry رُبط بـ Achieved مباشرة؟",
    },
]


def build_lexicon_report() -> Dict[str, Any]:
    return {
        "report_type": "epistemic_leakage_lexicon",
        "lexicon_version": LEXICON_VERSION,
        "not": "automated governance scoring · gate · veto",
        "purpose_ar": (
            "institutional semantic drift vocabulary — "
            "epistemic leakage indicators for workshop deliberation"
        ),
        "leakage_types": LEAKAGE_TYPES,
        "entries": LEXICON_ENTRIES,
        "usage_ar": [
            "سجّل العبارات الحرفية في Section E language samples",
            "استخدم lexicon كمرجع facilitator — ليس classifier آلي",
            "ناقش patterns في نهاية الورشة — ليس pass/fail per submission",
        ],
    }


def _normalize_text(text: str) -> str:
    t = (text or "").strip().lower()
    for src, dst in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي")):
        t = t.replace(src, dst)
    return re.sub(r"\s+", " ", t)


def match_leakage_in_text(text: str) -> List[Dict[str, Any]]:
    """
    Advisory matches only — facilitator confirms in workshop.
    Returns matched lexicon entries with matched phrase span.
    """
    if not text or not text.strip():
        return []
    norm = _normalize_text(text)
    matches: List[Dict[str, Any]] = []
    for entry in LEXICON_ENTRIES:
        for field in ("phrase_ar", "phrase_en"):
            phrase = entry.get(field) or ""
            if not phrase:
                continue
            pnorm = _normalize_text(phrase)
            if pnorm in norm or norm in pnorm:
                matches.append({
                    "entry_id": entry["entry_id"],
                    "matched_phrase": phrase,
                    "matched_field": field,
                    "leakage_type": entry["leakage_type"],
                    "leakage_type_label_ar": LEAKAGE_TYPES.get(entry["leakage_type"], ""),
                    "interpretation_ar": entry.get("interpretation_ar"),
                    "facilitator_prompt_ar": entry.get("facilitator_prompt_ar"),
                    "advisory_only": True,
                })
                break
    return matches


def analyze_language_samples(
    samples: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Aggregate advisory leakage patterns across workshop language samples."""
    all_matches: List[Dict[str, Any]] = []
    by_type: Dict[str, List[Dict[str, Any]]] = {}
    by_submission: List[Dict[str, Any]] = []

    for sample in samples:
        sid = sample.get("submission_id")
        text = str(sample.get("samples_ar") or sample.get("text") or "")
        matched = match_leakage_in_text(text)
        if matched:
            by_submission.append({
                "submission_id": sid,
                "samples_ar": text,
                "advisory_matches": matched,
            })
            all_matches.extend(matched)
            for m in matched:
                lt = m["leakage_type"]
                by_type.setdefault(lt, []).append({**m, "submission_id": sid})

    pattern_notes: List[str] = []
    if by_type.get("implicit_runtime_verification"):
        pattern_notes.append(
            "pattern: implicit runtime verification — semantic restraint may be weakening"
        )
    if by_type.get("modality_dominance"):
        pattern_notes.append(
            "pattern: modality dominance — video/screenshot treated as proof"
        )
    if by_type.get("criterion_escalation"):
        pattern_notes.append(
            "pattern: criterion escalation — observation → Achieved language"
        )
    if by_type.get("provenance_overreach"):
        pattern_notes.append(
            "pattern: provenance overreach — replay absolutized"
        )
    if not all_matches:
        pattern_notes.append(
            "no lexicon matches in recorded samples — or samples not yet captured"
        )

    return {
        "report_type": "epistemic_leakage_analysis",
        "not": "score · gate · automated classification",
        "lexicon_version": LEXICON_VERSION,
        "match_count": len(all_matches),
        "unique_leakage_types": sorted(by_type.keys()),
        "patterns_by_type": {k: v for k, v in sorted(by_type.items())},
        "per_submission": by_submission,
        "pattern_notes_ar": pattern_notes,
        "facilitator_reminder_ar": (
            "advisory matches only — discuss patterns, not pass/fail per submission"
        ),
    }


def enrich_epistemic_synthesis(
    synthesis: Dict[str, Any],
    *,
    observations: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Attach advisory lexicon analysis to epistemic behavioural evidence."""
    samples = synthesis.get("linguistic_leakage_examples") or []
    if observations and not samples:
        samples = [
            {
                "submission_id": o.get("submission_id"),
                "samples_ar": (
                    (o.get("section_e_epistemic_behaviour") or {}).get(
                        "reviewer_language_samples_ar"
                    )
                ),
            }
            for o in observations
            if (o.get("section_e_epistemic_behaviour") or {}).get(
                "reviewer_language_samples_ar"
            )
        ]
    leakage = analyze_language_samples(samples)
    out = dict(synthesis)
    out["leakage_lexicon_analysis"] = leakage
    if leakage.get("pattern_notes_ar"):
        existing = list(out.get("facilitator_interpretation_ar") or [])
        for note in leakage["pattern_notes_ar"]:
            if note not in existing:
                existing.append(note)
        out["facilitator_interpretation_ar"] = existing
    return out
