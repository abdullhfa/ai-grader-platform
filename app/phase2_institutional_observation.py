"""
Phase 2 — Live Institutional Behaviour Observation.

Architecture/instrumentation is not evidence.
Complete Phase 2 = historically grounded human epistemic evidence.

Observe only. No training, correction, intervention, or facilitator steering mid-session.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

WORKSHOP_DIR = Path("app/calibration/human_cohort_workshop")
PHASE2_STATE_FILE = "phase2_cohort_state.json"
RITUAL_READING_FILE = "phase2_ritual_reading_{batch_id}.json"
PHASE2_ID = "PHASE2_INSTITUTIONAL_OBSERVATION_v1"
COOLING_PERIOD_DAYS_MIN = 3
COOLING_PERIOD_DAYS_DEFAULT = 5
TARGET_SUBMISSIONS_MIN = 20
TARGET_SUBMISSIONS_MAX = 30

OBSERVE_ONLY_RULES_AR = [
    "observe only — لا training ولا correction ولا intervention ولا semantic steering",
    "replay first — صمت حتى يُفتح Authority Replay",
    "Section E قبل Section D — epistemic behaviour precedes trust sentiment",
    "سجّل language samples حرفياً — حتى العبارات «العادية»",
    "سجّل absence — contradiction غير مذكورة، replay متأخر، uncertainty اختفت",
    "لا sandbox · لا v2 · لا L4 expansion · لا constitutional evolution حتى إكمال Phase 2",
]

GOLDEN_ABSENCE_SIGNALS = [
    "contradiction_not_mentioned",
    "replay_not_opened_promptly",
    "uncertainty_disappeared",
    "human_corroboration_not_requested",
    "modality_accepted_without_hold",
]

RITUAL_READING_LENSES = [
    {
        "id": "replay_timing",
        "label_ar": "replay timing",
        "question_ar": "متى فُتح replay؟ هل سبق أي verbal judgment؟",
        "why_ar": "provenance discipline",
    },
    {
        "id": "hesitation_disappearance",
        "label_ar": "hesitation disappearance",
        "question_ar": "أين اختفت الترددات بعد رؤية runtime evidence؟",
        "why_ar": "ambiguity collapse",
    },
    {
        "id": "contradiction_silence",
        "label_ar": "contradiction silence",
        "question_ar": "أي contradictions بقيت غير مذكورة في النقاش؟",
        "why_ar": "passive legitimacy",
    },
    {
        "id": "persuasive_screenshots",
        "label_ar": "emotionally persuasive screenshots",
        "question_ar": "هل screenshots/visuals سرّعت اليقين دون HOLD؟",
        "why_ar": "observational acceleration",
    },
    {
        "id": "implicit_authority_phrases",
        "label_ar": "«واضح أنها شغالة» وما شابه",
        "question_ar": "أي عبارات حوّلت observation إلى legitimacy ضمنياً؟",
        "why_ar": "implicit authority formation",
    },
    {
        "id": "silence_as_closure",
        "label_ar": "silence itself",
        "question_ar": "أين كان الصمت ضغط إغلاق بدلاً من epistemic restraint؟",
        "why_ar": "closure pressure",
    },
]

PHASE2_WORKFLOW_STEPS = [
    {"id": "workshop", "label_ar": "workshop حقيقية (20–30 submission)", "status_key": "observation_active"},
    {"id": "synthesis", "label_ar": "epistemic synthesis حقيقي", "status_key": "synthesis"},
    {"id": "cooling", "label_ar": "cooling period (3–7 أيام)", "status_key": "cooling_period"},
    {"id": "ritual_reading", "label_ar": "ritual reading بطيء", "status_key": "ritual_reading"},
    {"id": "semantic_memory", "label_ar": "semantic memory record", "status_key": "semantic_memory"},
    {"id": "epoch_deliberation", "label_ar": "epoch deliberation", "status_key": "epoch_deliberation"},
]


def _ensure_dir() -> Path:
    WORKSHOP_DIR.mkdir(parents=True, exist_ok=True)
    return WORKSHOP_DIR


def _load_state() -> Dict[str, Any]:
    path = _ensure_dir() / PHASE2_STATE_FILE
    if not path.exists():
        return {"version": 1, "cohorts": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "cohorts": {}}


def _save_state(state: Dict[str, Any]) -> None:
    path = _ensure_dir() / PHASE2_STATE_FILE
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _ritual_path(batch_id: int) -> Path:
    return _ensure_dir() / RITUAL_READING_FILE.format(batch_id=batch_id)


def _parse_utc(ts: Optional[str]) -> Optional[datetime.datetime]:
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def _cooling_active(cohort: Dict[str, Any]) -> bool:
    if cohort.get("status") != "cooling_period":
        return False
    ends = _parse_utc(cohort.get("cooling_period_ends_at"))
    if not ends:
        return True
    now = datetime.datetime.now(datetime.timezone.utc)
    return now < ends.replace(tzinfo=datetime.timezone.utc)


def _empty_ritual_reading(batch_id: int) -> Dict[str, Any]:
    return {
        "batch_id": batch_id,
        "phase": PHASE2_ID,
        "core_question_ar": (
            "how certainty psychologically stabilized "
            "under bounded runtime observability"
        ),
        "not_for": ["who was wrong", "leakage count", "readiness score"],
        "lenses": {
            lens["id"]: {"notes_ar": "", "observed": None}
            for lens in RITUAL_READING_LENSES
        },
        "facilitator_reflection_ar": "",
        "completed_at": None,
    }


def activate_phase2_cohort(
    *,
    batch_id: int,
    facilitator: str = "",
    target_submissions: int = 25,
    notes_ar: str = "",
) -> Dict[str, Any]:
    """Register batch as Phase 2 live observation cohort (real submissions only)."""
    state = _load_state()
    now = datetime.datetime.utcnow().isoformat() + "Z"
    key = str(batch_id)
    cohort = {
        "phase": PHASE2_ID,
        "batch_id": batch_id,
        "status": "observation_active",
        "mode": "observe_only",
        "activated_at": now,
        "facilitator": facilitator,
        "target_submissions": min(max(target_submissions, TARGET_SUBMISSIONS_MIN), TARGET_SUBMISSIONS_MAX),
        "notes_ar": notes_ar,
        "workshop_completed_at": None,
        "cooling_period_started_at": None,
        "cooling_period_ends_at": None,
        "epistemic_synthesis_generated_at": None,
        "ritual_reading_completed_at": None,
        "semantic_memory_recorded_at": None,
        "epoch_deliberation_started_at": None,
        "epoch_deliberation_completed_at": None,
        "rules_ar": OBSERVE_ONLY_RULES_AR,
    }
    state.setdefault("cohorts", {})[key] = cohort
    _save_state(state)
    _ritual_path(batch_id).write_text(
        json.dumps(_empty_ritual_reading(batch_id), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"ok": True, "cohort": cohort}


def complete_workshop_and_start_cooling(
    *,
    batch_id: int,
    cooling_days: int = COOLING_PERIOD_DAYS_DEFAULT,
    observation_count: int = 0,
    force: bool = False,
) -> Dict[str, Any]:
    """Mark workshop complete; start mandatory cooling period."""
    state = _load_state()
    key = str(batch_id)
    cohort = (state.get("cohorts") or {}).get(key)
    if not cohort:
        return {"ok": False, "code": "cohort_not_registered", "message_ar": "الدفعة غير مسجّلة في Phase 2"}

    target = int(cohort.get("target_submissions") or TARGET_SUBMISSIONS_MIN)
    if observation_count < TARGET_SUBMISSIONS_MIN and not force:
        return {
            "ok": False,
            "code": "insufficient_observations",
            "message_ar": (
                f"Phase 2 غير مكتمل: {observation_count}/{TARGET_SUBMISSIONS_MIN} observations. "
                "workshop حقيقية = 20–30 submission مع facilitators حقيقيين."
            ),
            "observation_count": observation_count,
            "target_min": TARGET_SUBMISSIONS_MIN,
            "target": target,
        }

    now = datetime.datetime.utcnow()
    days = max(COOLING_PERIOD_DAYS_MIN, min(int(cooling_days or COOLING_PERIOD_DAYS_DEFAULT), 7))
    ends = now + datetime.timedelta(days=days)
    cohort["status"] = "cooling_period"
    cohort["workshop_completed_at"] = now.isoformat() + "Z"
    cohort["cooling_period_started_at"] = cohort["workshop_completed_at"]
    cohort["cooling_period_ends_at"] = ends.isoformat() + "Z"
    cohort["observations_at_completion"] = observation_count
    state["cohorts"][key] = cohort
    _save_state(state)
    return {
        "ok": True,
        "cohort": cohort,
        "message_ar": (
            f"workshop marked complete ({observation_count} observations). "
            f"cooling period {days} أيام — ثم ritual reading فقط. "
            "ممنوع: new rules · mitigations · freeze evolution · leakage controls."
        ),
    }


def mark_epistemic_synthesis_generated(
    batch_id: int,
    *,
    observation_count: int = 0,
) -> Dict[str, Any]:
    state = _load_state()
    key = str(batch_id)
    cohort = (state.get("cohorts") or {}).get(key)
    if not cohort:
        return {"ok": False, "code": "cohort_not_registered"}

    if observation_count < 1:
        return {
            "ok": False,
            "code": "no_human_evidence",
            "message_ar": "لا epistemic synthesis بدون observations بشرية حقيقية.",
        }

    cohort["epistemic_synthesis_generated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    cohort["epistemic_synthesis_observation_count"] = observation_count
    if cohort.get("status") == "observation_active":
        cohort["status"] = "synthesis_generated"
    state["cohorts"][key] = cohort
    _save_state(state)
    return {
        "ok": True,
        "cohort": cohort,
        "evidence_quality_ar": (
            "historically grounded institutional behavioural evidence"
            if observation_count >= TARGET_SUBMISSIONS_MIN
            else f"partial ({observation_count}/{TARGET_SUBMISSIONS_MIN}) — workshop not yet complete"
        ),
    }


def advance_to_ritual_reading(batch_id: int) -> Dict[str, Any]:
    """After cooling ends — open ritual reading phase."""
    state = _load_state()
    key = str(batch_id)
    cohort = (state.get("cohorts") or {}).get(key)
    if not cohort:
        return {"ok": False, "code": "cohort_not_registered"}

    if _cooling_active(cohort):
        return {
            "ok": False,
            "code": "cooling_period_active",
            "message_ar": "cooling period لم ينتهِ — لا ritual reading بعد.",
            "cooling_period_ends_at": cohort.get("cooling_period_ends_at"),
        }
    if not cohort.get("epistemic_synthesis_generated_at"):
        return {
            "ok": False,
            "code": "synthesis_required",
            "message_ar": "ولّد epistemic synthesis أولاً قبل ritual reading.",
        }

    cohort["status"] = "ritual_reading"
    cohort["ritual_reading_started_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    state["cohorts"][key] = cohort
    _save_state(state)
    return {"ok": True, "cohort": cohort}


def load_ritual_reading(batch_id: int) -> Dict[str, Any]:
    path = _ritual_path(batch_id)
    if not path.exists():
        data = _empty_ritual_reading(batch_id)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty_ritual_reading(batch_id)


def save_ritual_reading(batch_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = load_ritual_reading(batch_id)
    lenses_in = payload.get("lenses") or {}
    for lens in RITUAL_READING_LENSES:
        lid = lens["id"]
        if lid in lenses_in:
            data["lenses"][lid] = {
                "notes_ar": str(lenses_in[lid].get("notes_ar") or "").strip(),
                "observed": lenses_in[lid].get("observed"),
            }
    data["facilitator_reflection_ar"] = str(payload.get("facilitator_reflection_ar") or "").strip()
    if payload.get("mark_complete"):
        data["completed_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        state = _load_state()
        cohort = (state.get("cohorts") or {}).get(str(batch_id)) or {}
        if cohort:
            cohort["status"] = "ritual_reading_complete"
            cohort["ritual_reading_completed_at"] = data["completed_at"]
            state.setdefault("cohorts", {})[str(batch_id)] = cohort
            _save_state(state)
    _ritual_path(batch_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "ritual_reading": data}


def mark_semantic_memory_recorded(batch_id: int) -> None:
    state = _load_state()
    cohort = (state.get("cohorts") or {}).get(str(batch_id))
    if not cohort:
        return
    cohort["semantic_memory_recorded_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    cohort["status"] = "semantic_memory_recorded"
    state.setdefault("cohorts", {})[str(batch_id)] = cohort
    _save_state(state)


def assert_semantic_memory_allowed(batch_id: int) -> Tuple[bool, Dict[str, Any]]:
    cohort = (_load_state().get("cohorts") or {}).get(str(batch_id))
    if not cohort:
        return True, {}
    if not cohort.get("ritual_reading_completed_at"):
        return False, {
            "code": "ritual_reading_required",
            "message_ar": (
                "semantic memory بعد ritual reading فقط — "
                "ليس مباشرة بعد الورشة. "
                "اقرأ: replay timing · hesitation · contradiction silence · "
                "implicit phrases · silence as closure."
            ),
        }
    if _cooling_active(cohort):
        return False, {
            "code": "cooling_period_active",
            "message_ar": "cooling period لم ينتهِ — انتظر قبل semantic memory.",
        }
    return True, {}


def assert_epoch_deliberation_allowed(batch_id: int) -> Tuple[bool, Dict[str, Any]]:
    cohort = (_load_state().get("cohorts") or {}).get(str(batch_id))
    if not cohort:
        return True, {}
    if not cohort.get("semantic_memory_recorded_at"):
        return False, {
            "code": "semantic_memory_required",
            "message_ar": (
                "epoch deliberation بعد synthesis + cooling + ritual reading + semantic memory — "
                "ليس مباشرة بعد metrics."
            ),
        }
    return True, {}


def is_governance_expansion_locked(batch_id: int) -> bool:
    """L4 / sandbox / constitutional evolution locked until Phase 2 fully complete."""
    cohort = (_load_state().get("cohorts") or {}).get(str(batch_id))
    if not cohort:
        return False
    return cohort.get("status") not in (
        "epoch_deliberation_complete",
        "phase3_discussion_ready",
        "phase3_calibration_ready",
    )


def build_workflow_progress(batch_id: int, *, observation_count: int = 0) -> Dict[str, Any]:
    cohort = (_load_state().get("cohorts") or {}).get(str(batch_id))
    if not cohort:
        return {"registered": False, "steps": []}

    status = cohort.get("status") or "observation_active"
    cooling_active = _cooling_active(cohort)
    ritual = load_ritual_reading(batch_id)

    def step_state(step_id: str) -> str:
        if step_id == "workshop":
            if status == "observation_active":
                return "active" if observation_count < TARGET_SUBMISSIONS_MIN else "ready"
            return "done"
        if step_id == "synthesis":
            if cohort.get("epistemic_synthesis_generated_at"):
                return "done"
            if observation_count >= TARGET_SUBMISSIONS_MIN:
                return "ready"
            return "pending"
        if step_id == "cooling":
            if cohort.get("workshop_completed_at"):
                return "active" if cooling_active else "done"
            return "pending"
        if step_id == "ritual_reading":
            if cohort.get("ritual_reading_completed_at"):
                return "done"
            if status == "ritual_reading" or (not cooling_active and cohort.get("workshop_completed_at")):
                return "active" if cohort.get("epistemic_synthesis_generated_at") else "pending"
            return "pending"
        if step_id == "semantic_memory":
            if cohort.get("semantic_memory_recorded_at"):
                return "done"
            if cohort.get("ritual_reading_completed_at"):
                return "ready"
            return "pending"
        if step_id == "epoch_deliberation":
            if cohort.get("epoch_deliberation_completed_at"):
                return "done"
            if cohort.get("semantic_memory_recorded_at"):
                return "ready"
            return "pending"
        return "pending"

    steps = []
    for step in PHASE2_WORKFLOW_STEPS:
        steps.append({**step, "state": step_state(step["id"])})

    return {
        "registered": True,
        "current_focus_ar": (
            "workshop حقيقية — observe only"
            if status == "observation_active"
            else "cooling + ritual reading — لا governance edits"
            if cooling_active
            else "ritual reading بطيء — how certainty stabilized"
            if status in ("ritual_reading", "synthesis_generated", "cooling_period")
            and not cohort.get("ritual_reading_completed_at")
            else "semantic memory ثم epoch deliberation"
            if not cohort.get("semantic_memory_recorded_at")
            else "epoch deliberation — لا Phase 3 بعد"
        ),
        "observation_count": observation_count,
        "target_min": TARGET_SUBMISSIONS_MIN,
        "target_max": TARGET_SUBMISSIONS_MAX,
        "has_human_evidence": observation_count >= TARGET_SUBMISSIONS_MIN,
        "architecture_only": observation_count < TARGET_SUBMISSIONS_MIN,
        "steps": steps,
        "ritual_reading_lenses": RITUAL_READING_LENSES,
        "ritual_reading_complete": bool(ritual.get("completed_at")),
        "governance_expansion_locked": is_governance_expansion_locked(batch_id),
    }


def get_phase2_cohort_state(batch_id: int, *, observation_count: int = 0) -> Dict[str, Any]:
    state = _load_state()
    cohort = (state.get("cohorts") or {}).get(str(batch_id))
    if not cohort:
        return {
            "registered": False,
            "phase": PHASE2_ID,
            "batch_id": batch_id,
            "mode": "observe_only",
            "rules_ar": OBSERVE_ONLY_RULES_AR,
            "golden_absence_signals": GOLDEN_ABSENCE_SIGNALS,
            "workflow": build_workflow_progress(batch_id, observation_count=observation_count),
            "core_question_ar": (
                "ماذا تفعل قابلية ملاحظة runtime بالحكم المؤسسي؟"
            ),
            "not_yet": "أدلة سلوكية مؤسسية مُؤَسَّسة تاريخياً",
        }
    cooling_active = _cooling_active(cohort)
    return {
        "registered": True,
        **cohort,
        "cooling_period_active": cooling_active,
        "golden_absence_signals": GOLDEN_ABSENCE_SIGNALS,
        "watch_metric_ar": (
            "implicit legitimacy acceleration — "
            "replay richer + screenshots clearer → ambiguity يقل نفسياً بدون تغيير authority"
        ),
        "workflow": build_workflow_progress(batch_id, observation_count=observation_count),
        "governance_expansion_locked": is_governance_expansion_locked(batch_id),
        "core_question_ar": (
            "ماذا تفعل قابلية ملاحظة runtime بالحكم المؤسسي؟"
        ),
        "not_yet": (
            None
            if observation_count >= TARGET_SUBMISSIONS_MIN
            and cohort.get("ritual_reading_completed_at")
            else "أدلة سلوكية مؤسسية مُؤَسَّسة تاريخياً"
        ),
    }


def build_phase2_exit_checklist(
    *,
    synthesis: Dict[str, Any],
    epistemic: Dict[str, Any],
    batch_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Phase 3 calibration gate — only after Phase 2 fully complete."""
    pilot_gate = synthesis.get("pilot_gate") or {}
    cohort = (_load_state().get("cohorts") or {}).get(str(batch_id or "")) or {}
    phase2_complete = bool(
        cohort.get("ritual_reading_completed_at")
        and cohort.get("semantic_memory_recorded_at")
        and cohort.get("workshop_completed_at")
    )

    items: List[Dict[str, Any]] = [
        {
            "id": "phase2_human_evidence",
            "label_ar": "Phase 2 human epistemic evidence collected",
            "met": phase2_complete,
        },
        {
            "id": "replay_trusted",
            "label_ar": "replay trusted",
            "met": (synthesis.get("replay_usage") or {}).get("replay_opened_count", 0) > 0,
        },
        {
            "id": "contradictions_visible",
            "label_ar": "contradictions بقيت visible",
            "met": pilot_gate.get("contradiction_visibility_ok") is not False,
        },
        {
            "id": "l3_confusion_low",
            "label_ar": "L3 confusion منخفض جداً",
            "met": (synthesis.get("l3_confusion_map") or {}).get("manual_confusion_count", 99) == 0,
        },
        {
            "id": "no_silent_s5",
            "label_ar": "no silent S5",
            "met": pilot_gate.get("silent_s5") is not True,
        },
        {
            "id": "facilitator_restraint",
            "label_ar": "facilitators حافظوا على restraint (observe only)",
            "met": phase2_complete,
        },
        {
            "id": "certainty_not_auto_legitimacy",
            "label_ar": "certainty لم تتحول تلقائياً إلى legitimacy",
            "met": bool(epistemic.get("total_observations")),
        },
    ]
    met = sum(1 for i in items if i["met"])
    return {
        "phase": "phase3_institutional_evidence_calibration_gate",
        "phase3_name": "Institutional Evidence Calibration",
        "core_question_ar": (
            "how much institutional confidence should each evidence type legitimately carry?"
        ),
        "design_doc": "app/calibration/EVIDENCE_WEIGHT_CALIBRATION_v1.md",
        "items": items,
        "met_count": met,
        "total": len(items),
        "ready_for_phase3_calibration": phase2_complete and met >= 6,
        "ready_for_phase3_discussion": phase2_complete and met >= 6,
        "note_ar": (
            "Phase 3 = bounded evidence legitimacy models — "
            "ليس runtime expansion ولا silent scoring engine. "
            "L4 sandbox منطقي فقط داخل calibrated evidence ecology."
        ),
    }
