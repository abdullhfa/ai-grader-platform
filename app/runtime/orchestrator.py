"""Runtime session orchestrator — Phase 1 production entry point."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.core.logging_setup import log_structured
from app.core.production_config import get_production_config
from app.governance_freeze_registry import is_l4_sandbox_permitted
from app.runtime_engines.base import RuntimeSession, SessionStatus
from app.runtime_engines.registry import get_engine_registry, resolve_engine
from app.runtime_engines.normalization import normalize_runtime_manifest
from app.submission.failsafe import wrap_failsafe_observation, wrap_failsafe_session_result

logger = logging.getLogger("ai_grader.runtime.orchestrator")


def infer_submission_root(
    paths: Sequence[str],
    *,
    student_name: str = "",
) -> Optional[Path]:
    """Pick a stable root directory/file from expanded submission paths."""
    if paths:
        try:
            from app.godot_submission_utils import find_godot_submission_root

            resolved = find_godot_submission_root(
                paths[0],
                student_name=student_name or "",
            )
            if resolved.is_dir():
                return resolved
        except Exception:
            pass

    candidates: List[Path] = []
    for raw in paths or []:
        p = Path(raw)
        if p.is_file():
            candidates.append(p.parent)
        elif p.is_dir():
            candidates.append(p)

    if not candidates:
        return None

    candidates.sort(key=lambda item: (len(item.parts), str(item)))
    return candidates[0]


def run_runtime_session(
    submission_key: str,
    root: Path,
    *,
    timeout_seconds: Optional[int] = None,
    enable_web_browser_automation: bool = False,
    enable_android_emulator_automation: bool = False,
    enable_gamemaker_runtime_verification: bool = False,
    enable_scratch_runtime_verification: bool = False,
) -> Dict[str, Any]:
    """Execute a single runtime engine session for a submission root."""
    cfg = get_production_config()
    if not cfg.enable_l4_sandbox or not is_l4_sandbox_permitted():
        return wrap_failsafe_session_result(
            {
                "status": "gated",
                "reason": "L4_sandbox_not_permitted",
                "engine": None,
            },
            root=root,
            submission_key=submission_key,
        )

    engine_cls = resolve_engine(root)
    if not engine_cls:
        return wrap_failsafe_session_result(
            {
                "status": "skipped",
                "reason": "no_engine_match",
                "root": str(root),
            },
            root=root,
            submission_key=submission_key,
        )

    session = RuntimeSession.create(
        engine=engine_cls.engine_id,
        submission_key=submission_key,
        root=root,
    )
    if enable_web_browser_automation:
        session.signals["enable_web_browser_automation"] = True
    if enable_android_emulator_automation:
        session.signals["enable_android_emulator_automation"] = True
    if enable_gamemaker_runtime_verification:
        session.signals["enable_gamemaker_runtime_verification"] = True
    if enable_scratch_runtime_verification:
        session.signals["enable_scratch_runtime_verification"] = True
    engine = engine_cls()
    effective_timeout = timeout_seconds or min(
        cfg.sandbox_timeout_seconds, engine.max_timeout_seconds
    )

    try:
        session.status = SessionStatus.PREPARING
        engine.prepare(session)
        if session.status not in (SessionStatus.SKIPPED, SessionStatus.FAILED):
            session.status = SessionStatus.RUNNING
            engine.execute(session, timeout_seconds=effective_timeout)
        evidence = engine.collect_evidence(session)
        evidence["normalized"] = normalize_runtime_manifest(evidence)
        if session.status == SessionStatus.RUNNING:
            session.status = SessionStatus.COMPLETED
            evidence["status"] = SessionStatus.COMPLETED.value
        else:
            evidence["status"] = session.status.value
        return wrap_failsafe_session_result(
            evidence,
            root=root,
            submission_key=submission_key,
        )
    except Exception as exc:
        logger.exception("Runtime session failed for %s", submission_key)
        session.status = SessionStatus.FAILED
        session.errors.append(str(exc))
        evidence = engine.collect_evidence(session)
        evidence["normalized"] = normalize_runtime_manifest(evidence)
        return wrap_failsafe_session_result(
            evidence,
            root=root,
            submission_key=submission_key,
        )
    finally:
        try:
            engine.cleanup(session)
        except Exception:
            pass


def run_runtime_observation(
    submission_paths: Sequence[str],
    *,
    submission_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    student_name: str = "",
    enable_smoke_test: bool = True,
    enable_web_browser_automation: bool = False,
    enable_android_emulator_automation: bool = False,
    enable_gamemaker_runtime_verification: bool = False,
    enable_scratch_runtime_verification: bool = False,
    grading_mode: str | None = None,
) -> Dict[str, Any]:
    """
    Orchestrated L4 runtime observation across detected engines.

    Integrates with existing sandbox_engine output shape for backward compatibility.
    """
    cfg = get_production_config()

    if not cfg.enable_l4_sandbox or not is_l4_sandbox_permitted():
        return {
            "status": "gated",
            "reason": "L4_sandbox_not_permitted",
            "observation_mode": "gated_stub",
            "platform_analyses": [],
        }

    if not submission_paths:
        return {
            "status": "skipped",
            "reason": "no_submission_paths",
            "platform_analyses": [],
        }

    submission_key = student_name or f"submission_{submission_id or 'unknown'}"
    root = infer_submission_root(submission_paths, student_name=student_name)
    if not root:
        return {
            "status": "skipped",
            "reason": "no_submission_root",
            "platform_analyses": [],
        }

    from app.core.production_config import resolve_sandbox_timeout_seconds

    smoke_timeout = resolve_sandbox_timeout_seconds(grading_mode) if enable_smoke_test else 5
    session_result = run_runtime_session(
        submission_key,
        root,
        timeout_seconds=smoke_timeout,
        enable_web_browser_automation=enable_web_browser_automation,
        enable_android_emulator_automation=enable_android_emulator_automation,
        enable_gamemaker_runtime_verification=enable_gamemaker_runtime_verification,
        enable_scratch_runtime_verification=enable_scratch_runtime_verification,
    )

    platform_analyses: List[Dict[str, Any]] = []
    if session_result.get("engine"):
        platform_analyses.append(
            {
                "platform": session_result.get("engine"),
                "path": str(root),
                "status": session_result.get("status"),
                "signals": session_result.get("signals") or {},
                "session_id": session_result.get("session_id"),
            }
        )

    observation: Dict[str, Any] = {
        "status": session_result.get("status", "skipped"),
        "observation_mode": "orchestrated_runtime_v2",
        "runtime_session_id": session_result.get("session_id"),
        "submission_key": submission_key,
        "engine": session_result.get("engine"),
        "confidence_tier": session_result.get("confidence_tier"),
        "capabilities": session_result.get("capabilities"),
        "telemetry": session_result.get("telemetry"),
        "runtime_events": session_result.get("events"),
        "artifact_manifest": session_result.get("artifacts"),
        "platform_analyses": platform_analyses,
        "sandbox_engine_version": "2.1",
        "orchestrator_version": "2.0",
        "normalized": session_result.get("normalized"),
        "submission_validity": session_result.get("submission_validity"),
        "confidence_tier": session_result.get("confidence_tier"),
        "failsafe": session_result.get("failsafe"),
    }

    legacy_obs = (session_result.get("signals") or {}).get("legacy_observation")
    godot_obs = (session_result.get("signals") or {}).get("godot_observation")
    for nested in (legacy_obs, godot_obs):
        if not isinstance(nested, dict):
            continue
        observation.update(
            {
                k: nested.get(k)
                for k in (
                    "unity_observation_summary",
                    "visual_observation_summary",
                    "runtime_screenshots",
                    "runtime_observed",
                    "runtime_verified",
                    "crash_detected",
                    "freeze_possible",
                    "runtime_signal_graph",
                    "runtime_duration_seconds",
                    "artifact_analyses",
                )
                if nested.get(k) is not None
            }
        )
        if nested.get("runtime_evidence_promotion") is not None:
            observation["runtime_evidence_promotion"] = nested.get("runtime_evidence_promotion")
        if nested.get("partial_runtime_verified") is not None:
            observation["partial_runtime_verified"] = nested.get("partial_runtime_verified")
        if nested.get("pck_pairing") is not None:
            observation["pck_pairing"] = nested.get("pck_pairing")
        if legacy_obs.get("status"):
            observation["legacy_status"] = legacy_obs.get("status")

    # Web screenshots from orchestrator
    web_shots = session_result.get("screenshots") or []
    if web_shots and not observation.get("runtime_screenshots"):
        observation["runtime_screenshots"] = [
            {"path": p, "status": "captured", "source": "web_headless"}
            for p in web_shots
        ]
        observation["runtime_observed"] = session_result.get("status") == "completed"

    metrics = session_result.get("metrics") or {}
    observation["runtime_metrics"] = metrics
    if metrics.get("freeze_detected"):
        observation["freeze_possible"] = True
    if metrics.get("crash_detected"):
        observation["crash_detected"] = True

    session_signals = session_result.get("signals") or {}
    if session_result.get("engine") == "unity":
        if session_signals.get("unity_observation"):
            observation["unity_observation_summary"] = [session_signals["unity_observation"]]
        if session_signals.get("scene_validation"):
            observation["unity_scene_validation"] = session_signals["scene_validation"]
        if session_signals.get("screenshot_comparison"):
            observation["unity_screenshot_comparison"] = session_signals["screenshot_comparison"]
        if session_signals.get("merged_log_signals"):
            observation["unity_merged_log_signals"] = session_signals["merged_log_signals"]
        if session_signals.get("build_attempt"):
            observation["unity_build_attempt"] = session_signals["build_attempt"]
        if session_signals.get("playmode_attempt"):
            observation["unity_playmode_attempt"] = session_signals["playmode_attempt"]
        if session_signals.get("gameplay_video_path"):
            observation["gameplay_video_path"] = session_signals["gameplay_video_path"]
        if session_signals.get("play_session"):
            observation["unity_play_session"] = session_signals["play_session"]

    if session_result.get("engine") == "gamemaker":
        if session_signals.get("artifact_analysis"):
            observation["gamemaker_artifact_analysis"] = session_signals["artifact_analysis"]
        if session_signals.get("gamemaker_observation"):
            observation["gamemaker_observation_summary"] = session_signals["gamemaker_observation"]
        if session_signals.get("yyp_metadata"):
            observation["gamemaker_yyp_metadata"] = session_signals["yyp_metadata"]
        if session_signals.get("gamemaker_runtime_verification"):
            observation["gamemaker_runtime_verification"] = session_signals["gamemaker_runtime_verification"]
        if session_signals.get("object_inspection"):
            observation["gamemaker_object_inspection"] = session_signals["object_inspection"]
        if session_signals.get("gameplay_replay"):
            observation["gamemaker_gameplay_replay"] = session_signals["gameplay_replay"]
        if session_signals.get("build_pipeline"):
            observation["gamemaker_build_pipeline"] = session_signals["build_pipeline"]

        gm_obs = session_signals.get("gamemaker_observation")
        if isinstance(gm_obs, dict):
            for key in (
                "runtime_observed",
                "runtime_verified",
                "runtime_screenshots",
                "artifact_analyses",
                "runtime_signal_graph",
                "runtime_duration_seconds",
                "crash_detected",
                "freeze_possible",
            ):
                if gm_obs.get(key) is not None and observation.get(key) is None:
                    observation[key] = gm_obs[key]
            if gm_obs.get("status") == "completed":
                observation["status"] = "completed"

        gameplay_replay = session_signals.get("gameplay_replay") or {}
        replay_shots = gameplay_replay.get("screenshots") or []
        if replay_shots:
            existing = {
                str(s.get("path"))
                for s in (observation.get("runtime_screenshots") or [])
                if isinstance(s, dict) and s.get("path")
            }
            merged = list(observation.get("runtime_screenshots") or [])
            for raw_path in replay_shots:
                path = str(raw_path or "").strip()
                if not path or path in existing:
                    continue
                merged.append(
                    {
                        "path": path,
                        "status": "captured",
                        "source": "gameplay_replay",
                        "label": Path(path).stem,
                    }
                )
                existing.add(path)
            if merged:
                observation["runtime_screenshots"] = merged

        if gameplay_replay.get("gameplay_observed"):
            observation["runtime_verified"] = True
            observation["runtime_observed"] = True
        elif session_signals.get("functional_smoke_pass"):
            observation["runtime_verified"] = True
            observation["runtime_observed"] = True
        elif isinstance(gm_obs, dict) and gm_obs.get("runtime_observed"):
            observation["runtime_observed"] = True
            if gm_obs.get("runtime_verified"):
                observation["runtime_verified"] = True

        if session_signals.get("runtime_method"):
            observation["runtime_method"] = session_signals["runtime_method"]
        launch_assessment = session_signals.get("gamemaker_launch_assessment") or {}
        launch_skipped = (
            session_signals.get("runtime_method") == "gamemaker_static_only"
            or (isinstance(gm_obs, dict) and gm_obs.get("status") == "skipped")
            or launch_assessment.get("launch_allowed") is False
        )
        observation["game_launch_attempted"] = bool(
            not launch_skipped
            and (
                session_signals.get("functional_smoke_pass")
                or gameplay_replay.get("gameplay_observed")
                or (
                    gameplay_replay.get("method") in ("exe_smoke", "html5_headless")
                    and not gameplay_replay.get("skipped")
                )
            )
        )

    if session_result.get("engine") == "scratch":
        if session_signals.get("execution_graph"):
            observation["scratch_execution_graph"] = session_signals["execution_graph"]
        if session_signals.get("scratch_vm"):
            observation["scratch_vm"] = session_signals["scratch_vm"]
        if session_signals.get("scratch_runtime_verification"):
            observation["scratch_runtime_verification"] = session_signals["scratch_runtime_verification"]

    log_structured(
        "runtime_orchestrator_complete",
        submission_id=submission_id,
        engine=session_result.get("engine"),
        status=observation.get("status"),
    )

    # Phase 3: Gameplay Intelligence Pipeline (downstream — not inside runtime engine)
    try:
        from app.gameplay_ai.pipeline import analyze_from_runtime_observation

        gameplay_analysis = analyze_from_runtime_observation(observation)
        if gameplay_analysis:
            observation["gameplay_analysis"] = gameplay_analysis
            if gameplay_analysis.get("timeline"):
                observation["gameplay_timeline"] = gameplay_analysis["timeline"]
    except Exception:
        logger.exception("Gameplay AI pipeline failed (non-fatal)")

    return wrap_failsafe_observation(observation, root=root)
