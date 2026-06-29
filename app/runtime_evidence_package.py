"""
PRO v1 — Runtime Evidence Package (observational only).

Event → Evidence → Coverage → Governance → Grade
Does NOT set grades or criterion achievement directly.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.pro_engine_gameplay_governance import detect_primary_game_engine
from app.runtime_replay_viewer import path_to_upload_url

PACKAGE_VERSION = "runtime_evidence_package_v1"

_SCREENSHOT_SLOTS = (
    ("startup", ("launch", "startup", "pre_interaction")),
    ("5s", ("5s", "mid_runtime", "post_interaction")),
    ("15s", ("15s", "mid_runtime")),
    ("30s", ("30s", "pre_exit", "post_interaction")),
)

_REQ_EVENT_MAP: Dict[str, Tuple[str, ...]] = {
    "player_movement": ("movement_observed", "input_detected", "scene_transition"),
    "jump": ("jump_observed", "movement_observed"),
    "collect_items": ("collectible_interaction_observed", "score_changed"),
    "score_system": ("score_changed",),
    "enemy_interaction": ("enemy_interaction_observed", "game_over_seen"),
    "win_condition": ("win_screen_seen",),
    "lose_condition": ("game_over_seen",),
    "restart": ("restart_flow_observed",),
    "menu_ui": ("menu_detected", "launch_success"),
    "level_design": ("scene_transition",),
}


def _observation(obs: Dict[str, Any]) -> Dict[str, Any]:
    return obs or {}


def _signals(obs: Dict[str, Any]) -> Dict[str, Any]:
    graph = obs.get("runtime_signal_graph") or {}
    return graph.get("signals") or {}


def _semantics(obs: Dict[str, Any], inv: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from app.gameplay_semantic_verification import assess_gameplay_semantics

        return assess_gameplay_semantics(obs, inventory=inv) or {}
    except Exception:
        return {}


def _boot_gate(obs: Dict[str, Any], inv: Dict[str, Any]) -> Dict[str, Any]:
    signals = _signals(obs)
    analyses = obs.get("artifact_analyses") or []
    smoke_ok = any(
        a.get("smoke_result") in ("stable_window", "launch_ok")
        for a in analyses
        if isinstance(a, dict)
    )
    crash = bool(
        obs.get("crash_detected")
        or signals.get("crash") == "observed"
        or any(
            (a.get("signals") or {}).get("crash") == "observed"
            and a.get("smoke_result") not in ("stable_window", "launch_ok")
            for a in analyses
            if isinstance(a, dict)
        )
    )
    launch_attempted = bool(
        obs.get("runtime_observed")
        or obs.get("runtime_verified")
        or obs.get("status") == "completed"
        or smoke_ok
        or signals.get("runtime_launch_attempted")
    )
    window_detected = bool(
        obs.get("runtime_observed")
        or smoke_ok
        or any(
            s.get("status") == "captured"
            for s in (obs.get("runtime_screenshots") or [])
            if isinstance(s, dict)
        )
    )
    input_detected = signals.get("interaction_input_sent") == "yes" or signals.get(
        "automated_interaction_observed"
    ) == "yes" or signals.get("visual_response_to_input") in ("partial", "detected", "yes")

    launch_ms = 0
    metrics = obs.get("runtime_metrics") or {}
    if metrics.get("launch_time_ms"):
        launch_ms = int(metrics.get("launch_time_ms") or 0)
    elif obs.get("runtime_duration_seconds"):
        launch_ms = int(float(obs.get("runtime_duration_seconds") or 0) * 1000)

    duration_s = float(
        obs.get("runtime_duration_seconds")
        or metrics.get("runtime_duration_seconds")
        or (30 if smoke_ok else 0)
    )

    scene_changed = signals.get("scene_loaded") in ("yes", "partial") or signals.get(
        "level_transition"
    ) in ("partial", "detected", "yes")

    if crash and not smoke_ok:
        status = "FAIL"
    elif launch_attempted and (smoke_ok or obs.get("runtime_verified")):
        status = "PASS"
    elif launch_attempted:
        status = "PARTIAL"
    else:
        status = "SKIPPED"

    return {
        "runtime_status": status,
        "launch_success": status in ("PASS", "PARTIAL"),
        "launch_time_ms": launch_ms,
        "crash_detected": crash,
        "window_detected": window_detected,
        "input_detected": bool(input_detected),
        "scene_changed": bool(scene_changed),
        "runtime_duration_s": round(duration_s, 1),
    }


def _collect_runtime_screenshots(
    obs: Dict[str, Any],
    inv: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Gather screenshot refs from observation and inventory runtime sources."""
    collected: List[Dict[str, Any]] = []
    seen_paths: set[str] = set()

    def add_shot(shot: Any) -> None:
        if isinstance(shot, str) and shot.strip():
            path = shot.strip()
            if path in seen_paths:
                return
            seen_paths.add(path)
            collected.append(
                {
                    "path": path,
                    "status": "captured",
                    "label": Path(path).stem,
                }
            )
        elif isinstance(shot, dict):
            path = str(shot.get("path") or "").strip()
            if not path or path in seen_paths:
                return
            seen_paths.add(path)
            collected.append(shot)

    for shot in obs.get("runtime_screenshots") or []:
        add_shot(shot)

    inv = inv or {}
    rt_art = inv.get("runtime_artifacts") or {}
    if isinstance(rt_art, dict):
        for shot in rt_art.get("runtime_screenshots") or []:
            add_shot(shot)

    for key in ("gamemaker_observation_summary", "gamemaker_observation"):
        gm = obs.get(key) or inv.get(key) or {}
        if isinstance(gm, dict):
            for shot in gm.get("runtime_screenshots") or []:
                add_shot(shot)

    for key in ("gamemaker_gameplay_replay",):
        replay = obs.get(key) or inv.get(key) or {}
        if isinstance(replay, dict):
            for shot in replay.get("screenshots") or []:
                add_shot(shot)

    for analysis in obs.get("artifact_analyses") or inv.get("artifact_analyses") or []:
        if isinstance(analysis, dict):
            for shot in analysis.get("runtime_screenshots") or []:
                add_shot(shot)

    return collected


def _normalize_screenshots(
    obs: Dict[str, Any],
    inv: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    raw = _collect_runtime_screenshots(obs, inv)
    slots: Dict[str, Dict[str, Any]] = {}
    for shot in raw:
        label = str(shot.get("label") or shot.get("capture_type") or "").lower()
        path = str(shot.get("path") or "")
        stem = Path(path).stem.lower() if path else ""
        elapsed = shot.get("elapsed_seconds")
        for slot, aliases in _SCREENSHOT_SLOTS:
            if slot in slots:
                continue
            if (
                label in aliases
                or stem in aliases
                or stem == slot
                or (isinstance(elapsed, (int, float)) and _slot_from_elapsed(slot, elapsed))
            ):
                slots[slot] = {
                    "slot": slot,
                    "filename": f"{slot}.png",
                    "path": path,
                    "url": path_to_upload_url(path),
                    "label": label or stem or slot,
                    "elapsed_seconds": elapsed,
                    "status": shot.get("status") or "captured",
                }
    ordered: List[Dict[str, Any]] = []
    for slot, _aliases in _SCREENSHOT_SLOTS:
        if slot in slots:
            ordered.append(slots[slot])
    matched_paths = {row["path"] for row in ordered if row.get("path")}
    for shot in raw:
        path = str(shot.get("path") or "")
        if path and path not in matched_paths:
            ordered.append(
                {
                    "slot": Path(path).stem or "capture",
                    "filename": Path(path).name,
                    "path": path,
                    "url": path_to_upload_url(path),
                    "label": str(shot.get("label") or Path(path).stem or "capture"),
                    "elapsed_seconds": shot.get("elapsed_seconds"),
                    "status": shot.get("status") or "captured",
                }
            )
            matched_paths.add(path)
    return ordered


def _slot_from_elapsed(slot: str, elapsed: float) -> bool:
    try:
        e = elapsed if isinstance(elapsed, (int, float)) else float(elapsed)
    except (TypeError, ValueError):
        return False
    targets = {"startup": 2.0, "5s": 5.0, "15s": 15.0, "30s": 30.0}
    target = targets.get(slot)
    if target is None:
        return False
    return abs(e - target) <= 3.0


def _confidence(base: float, *, strong: bool = False) -> float:
    if strong:
        return min(0.99, base + 0.08)
    return round(max(0.0, min(0.99, base)), 2)


def _extract_events(
    obs: Dict[str, Any],
    inv: Dict[str, Any],
    boot: Dict[str, Any],
    semantics: Dict[str, Any],
) -> List[Dict[str, Any]]:
    signals = _signals(obs)
    events: List[Dict[str, Any]] = []

    def add(event: str, confidence: float, **extra: Any) -> None:
        row: Dict[str, Any] = {"event": event, "confidence": _confidence(confidence)}
        row.update(extra)
        events.append(row)

    if boot.get("launch_success"):
        add("launch_success", 0.95 if boot.get("runtime_status") == "PASS" else 0.75)
    if boot.get("window_detected"):
        add("window_detected", 0.9)
    if boot.get("input_detected"):
        add("input_detected", 0.85)
    if boot.get("scene_changed"):
        add("scene_transition", 0.8)

    moved = signals.get("player_moved") in ("detected", "yes", "observed")
    visual_resp = signals.get("visual_response_to_input") in ("partial", "detected", "yes")
    if moved or visual_resp or semantics.get("interaction_detected"):
        add(
            "movement_observed",
            0.92 if moved else 0.78,
            signal="player_moved" if moved else "visual_response_to_input",
        )

    if semantics.get("interaction_detected") and not moved:
        add("jump_observed", 0.55, note="weak_proxy_from_interaction")
    elif moved:
        add("jump_observed", 0.65, note="proxy_movement_only")

    if signals.get("score_changed") in ("detected", "yes", "observed") or semantics.get(
        "score_progression_detected"
    ):
        add("score_changed", 0.9 if semantics.get("score_progression_detected") else 0.7)

    if semantics.get("fail_state_detected") or signals.get("game_over") in (
        "detected",
        "yes",
        "observed",
    ):
        add("game_over_seen", 0.88)

    if semantics.get("win_state_detected") or semantics.get("gameplay_loop_complete"):
        add("win_screen_seen", 0.85 if semantics.get("win_state_detected") else 0.6)

    if semantics.get("restart_flow_detected"):
        add("restart_flow_observed", 0.82)

    if semantics.get("menu_navigation_detected"):
        add("menu_detected", 0.8)

    if semantics.get("health_or_lives_detected"):
        add("enemy_interaction_observed", 0.72, note="lives_or_health_signal")

    best: Dict[str, Dict[str, Any]] = {}
    for row in events:
        ev = row["event"]
        if ev not in best or row["confidence"] > best[ev]["confidence"]:
            best[ev] = row
    return list(best.values())


def _map_requirements(
    checklist: Dict[str, Any],
    events: Sequence[Dict[str, Any]],
    screenshots: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    event_names = {e["event"] for e in events}
    shot_files = [s.get("filename") or s.get("slot") for s in screenshots]
    mapping: List[Dict[str, Any]] = []
    for req in checklist.get("requirements") or []:
        if not isinstance(req, dict):
            continue
        req_id = str(req.get("id") or "")
        if not req_id:
            continue
        candidates = _REQ_EVENT_MAP.get(req_id, ())
        evidence = [e for e in candidates if e in event_names]
        if not evidence and req.get("mentioned_in_sources"):
            evidence = [e for e in event_names if e.endswith("_observed")][:1]
        if shot_files and evidence:
            evidence = list(evidence) + [shot_files[min(len(shot_files) - 1, 1)]]
        mapping.append(
            {
                "requirement": req_id,
                "label_ar": req.get("label_ar") or req_id,
                "evidence": evidence,
                "mentioned_in_sources": bool(req.get("mentioned_in_sources")),
            }
        )
    return mapping


def _requirement_confidence(
    mapping: Sequence[Dict[str, Any]],
    events: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_event = {e["event"]: float(e.get("confidence") or 0) for e in events}
    rows: List[Dict[str, Any]] = []
    for row in mapping:
        req = str(row.get("requirement") or "")
        evs = row.get("evidence") or []
        scores = [by_event[e] for e in evs if e in by_event]
        pct = round(100 * (sum(scores) / len(scores))) if scores else 0
        rows.append(
            {
                "requirement": req,
                "label_ar": row.get("label_ar") or req,
                "confidence_pct": pct,
            }
        )
    return rows


def _strength_label(
    boot: Dict[str, Any],
    events: Sequence[Dict[str, Any]],
) -> str:
    if boot.get("runtime_status") == "FAIL":
        return "WEAK"
    if not events:
        return "WEAK"
    confs = [float(e.get("confidence") or 0) for e in events]
    avg = sum(confs) / len(confs) if confs else 0.0
    if boot.get("runtime_status") == "PASS" and avg >= 0.85 and len(events) >= 3:
        return "STRONG"
    if boot.get("runtime_status") in ("PASS", "PARTIAL") and avg >= 0.7:
        return "MODERATE"
    return "WEAK"


def build_runtime_evidence_package(
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    requirement_checklist: Optional[Dict[str, Any]] = None,
    submission_paths: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    inv = artifact_inventory or {}
    obs = _observation(inv.get("runtime_observation_report") or {})
    checklist = requirement_checklist or {"requirements": [], "requirement_ids": []}
    engine = detect_primary_game_engine(inv, submission_paths=list(submission_paths or []))

    boot = _boot_gate(obs, inv)
    semantics = _semantics(obs, inv)
    events = _extract_events(obs, inv, boot, semantics)
    screenshots = _normalize_screenshots(obs, inv)
    requirement_mapping = _map_requirements(checklist, events, screenshots)
    req_confidence = _requirement_confidence(requirement_mapping, events)
    strength = _strength_label(boot, events)

    strength_ar = {
        "STRONG": "أدلة تشغيلية قوية",
        "MODERATE": "أدلة تشغيلية متوسطة — يُنصح بمراجعة سريعة",
        "WEAK": "أدلة تشغيلية ضعيفة — مراجعة يدوية",
    }.get(strength, strength)

    return {
        "version": PACKAGE_VERSION,
        "engine": engine if engine != "unknown" else None,
        "runtime_status": boot["runtime_status"],
        "launch_time_ms": boot["launch_time_ms"],
        "crash_detected": boot["crash_detected"],
        "window_detected": boot["window_detected"],
        "input_detected": boot["input_detected"],
        "scene_changed": boot["scene_changed"],
        "runtime_duration_s": boot["runtime_duration_s"],
        "screenshots": screenshots,
        "events": events,
        "requirement_mapping": requirement_mapping,
        "requirement_confidence": req_confidence,
        "runtime_evidence_strength": strength,
        "runtime_evidence_strength_ar": strength_ar,
        "disclaimer_ar": (
            "أدلة تشغيلية مرصودة فقط — لا تُعد اعتماداً للدرجة. "
            "المنح عبر Coverage ثم Governance."
        ),
        "does_not_imply_grade": True,
    }


def attach_runtime_evidence_package(
    grading_result: Dict[str, Any],
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    requirement_checklist: Optional[Dict[str, Any]] = None,
    submission_paths: Optional[Sequence[str]] = None,
    student_text: str = "",
    reference_solution: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    inv = artifact_inventory or grading_result.get("artifact_inventory") or {}
    checklist = requirement_checklist or grading_result.get("requirement_checklist")
    if not checklist:
        from app.requirement_checklist import build_requirement_checklist

        checklist = build_requirement_checklist(
            student_text=student_text or str(grading_result.get("student_text") or ""),
            reference_solution=reference_solution,
        )

    package = build_runtime_evidence_package(
        artifact_inventory=inv,
        requirement_checklist=checklist,
        submission_paths=submission_paths,
    )
    grading_result["requirement_checklist"] = checklist
    grading_result["runtime_evidence_package"] = package
    inv_out = grading_result.setdefault("artifact_inventory", inv)
    inv_out["requirement_checklist"] = checklist
    inv_out["runtime_evidence_package"] = package
    return {"checklist": checklist, "package": package}


def package_event_names(package: Optional[Dict[str, Any]]) -> set[str]:
    if not package:
        return set()
    return {str(e.get("event") or "") for e in (package.get("events") or []) if e.get("event")}
