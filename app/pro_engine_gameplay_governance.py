"""
PRO-only (grading_mode=deep): per-engine runtime & gameplay governance for Pearson BTEC game units.

Godot / Unity / GameMaker each have distinct launch paths; C.P6 and higher bands require
documented playtest, gameplay video, successful runtime+gameplay validation, or L5 human review.

BASIC (fast) must never import this module.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.btec_criteria_governance import _demote_row, _short_level

GOVERNANCE_VERSION = "pro_engine_gameplay_v1"

# Criteria that require playtest / gameplay / L5 (not exe/pck/screenshots alone).
_PLAYTEST_GATED_SHORT = frozenset({"P6", "M3", "D2", "D3"})

_ENGINE_DETECT_ORDER = ("godot", "unity", "gamemaker", "unreal")

_ENGINE_POLICIES: Dict[str, Dict[str, Any]] = {
    "godot": {
        "support_tier_ar": "ممتاز",
        "implementation_ease_ar": "سهل",
        "gameplay_validation_required": True,
        "unity_runtime_validation": False,
        "playtest_required": False,
        "human_review_required": False,
        "min_core_mechanics_for_cp6": 2,
        "require_game_launch_for_cp6": True,
        "launch_commands_ar": ["game.exe", "Godot.exe --path <project_folder>"],
        "project_markers": ("project.godot", "*.pck", "*.exe"),
    },
    "unity": {
        "support_tier_ar": "ممتاز",
        "implementation_ease_ar": "متوسط",
        "gameplay_validation_required": True,
        "unity_runtime_validation": True,
        "playtest_required": True,
        "human_review_required": False,
        "min_core_mechanics_for_cp6": 2,
        "require_game_launch_for_cp6": True,
        "launch_commands_ar": ["Game.exe (Build)", "Unity build ثم تشغيل"],
        "project_markers": ("Assets/", "ProjectSettings/", "Build/"),
        "supports_playmode_tests": True,
    },
    "gamemaker": {
        "support_tier_ar": "جيد",
        "implementation_ease_ar": "أصعب",
        "gameplay_validation_required": True,
        "unity_runtime_validation": False,
        "playtest_required": False,
        "human_review_required": True,
        "min_core_mechanics_for_cp6": 1,
        "require_game_launch_for_cp6": True,
        "launch_commands_ar": ["Game.exe"],
        "project_markers": (".yyp", ".win", ".exe"),
    },
    "unreal": {
        "support_tier_ar": "جيد",
        "implementation_ease_ar": "متوسط",
        "gameplay_validation_required": True,
        "unity_runtime_validation": False,
        "playtest_required": True,
        "human_review_required": False,
        "min_core_mechanics_for_cp6": 2,
        "require_game_launch_for_cp6": True,
        "launch_commands_ar": ["Game.exe (Windows build)", "Packaged build"],
        "project_markers": (".uproject", "Binaries/", "Content/"),
    },
}

_STRUCTURE_ONLY_METHODS = frozenset(
    {
        "godot_static_analysis",
        "godot_apk_pck_static_scan",
        "godot_pck_pairing_smoke",
        "pck_smoke",
        "pck_pairing",
        "structure_only",
        "observed_structure_only",
    }
)


def _detect_tools_from_paths(
    inv: Dict[str, Any],
    submission_paths: Optional[List[str]] = None,
) -> set[str]:
    detected: set[str] = set()
    joined = " ".join(p for p in (submission_paths or [])).lower()
    for raw in inv.get("intake_relative_paths") or []:
        joined += " " + str(raw).lower()
    markers = {
        "godot": ("project.godot", ".pck", ".gd", "godot"),
        "unity": ("assets/", ".unity", "assembly-csharp", "projectsettings"),
        "gamemaker": (".yyp", ".gml", "gamemaker", ".win"),
        "unreal": (".uproject", "unreal", "content/", "binaries/"),
    }
    for engine_id, keys in markers.items():
        if any(k in joined for k in keys):
            detected.add(engine_id)
    return detected


def detect_primary_game_engine(
    artifact_inventory: Optional[Dict[str, Any]] = None,
    *,
    submission_paths: Optional[List[str]] = None,
) -> str:
    """Resolve dominant engine: godot > unity > gamemaker > unknown."""
    inv = artifact_inventory or {}
    detected = _detect_tools_from_paths(inv, submission_paths)
    profile = inv.get("project_profile") or inv.get("ultra_light_project_profile") or {}
    for eng in profile.get("engines_detected") or profile.get("project_types") or []:
        detected.add(str(eng).lower().replace(" ", "_"))

    obs = inv.get("runtime_observation_report") or {}
    for analysis in obs.get("platform_analyses") or []:
        if isinstance(analysis, dict):
            e = str(analysis.get("engine") or "").lower()
            if e:
                detected.add(e)

    for preferred in _ENGINE_DETECT_ORDER:
        if preferred in detected:
            return preferred
    joined = " ".join(p for p in (submission_paths or [])).lower()
    for raw in inv.get("intake_relative_paths") or []:
        joined += " " + str(raw).lower()
    if "project.godot" in joined or ".pck" in joined or ".gd" in joined:
        return "godot"
    if "assets/" in joined or ".unity" in joined or "assembly-csharp" in joined:
        return "unity"
    if ".yyp" in joined or ".gml" in joined or "gamemaker" in joined:
        return "gamemaker"
    return "unknown"


def get_engine_policy(engine_id: str) -> Dict[str, Any]:
    base = dict(_ENGINE_POLICIES.get(engine_id) or _ENGINE_POLICIES["godot"])
    base["engine_id"] = engine_id if engine_id in _ENGINE_POLICIES else "unknown"
    if engine_id not in _ENGINE_POLICIES:
        base.update(
            {
                "support_tier_ar": "غير محدد",
                "implementation_ease_ar": "—",
                "human_review_required": True,
                "gameplay_validation_required": True,
            }
        )
    return base


def _runtime_method(obs: Dict[str, Any]) -> str:
    method = str(obs.get("observation_mode") or obs.get("runtime_method") or "").lower()
    if method:
        return method
    for analysis in obs.get("platform_analyses") or []:
        if isinstance(analysis, dict):
            sig = analysis.get("signals") or {}
            m = str(sig.get("runtime_method") or "").lower()
            if m:
                return m
    return str((obs.get("signals") or {}).get("runtime_method") or "").lower()


def _platform_signals(obs: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(obs.get("signals") or {})
    for analysis in obs.get("platform_analyses") or []:
        if isinstance(analysis, dict):
            sig = analysis.get("signals") or {}
            if isinstance(sig, dict):
                merged.update(sig)
    return merged


def is_structure_only_runtime(inv: Dict[str, Any]) -> bool:
    obs = inv.get("runtime_observation_report") or {}
    method = _runtime_method(obs)
    if method in _STRUCTURE_ONLY_METHODS or "static" in method or "pairing_smoke" in method:
        return True
    if obs.get("game_launch_attempted") is False:
        return True
    sig = _platform_signals(obs)
    if sig.get("pck_pairing") and not sig.get("game_launch_attempted"):
        return True
    rv = inv.get("runtime_validation") or {}
    smoke = rv.get("functional_smoke") or {}
    if smoke.get("reason") in (
        "structure_only_no_game_launch",
        "game_not_launched",
    ):
        return True
    return False


def _count_core_mechanics(checks: Dict[str, Any]) -> int:
    core = (
        "win_state",
        "lose_state",
        "scene_transition",
        "score_hud",
        "player_movement",
        "jump_mechanic",
    )
    return sum(1 for k in core if (checks.get(k) or {}).get("observed"))


def build_runtime_telemetry(
    artifact_inventory: Optional[Dict[str, Any]] = None,
    *,
    gameplay_checks: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    inv = artifact_inventory or {}
    obs = inv.get("runtime_observation_report") or {}
    sig = _platform_signals(obs)
    rv = inv.get("runtime_validation") or {}
    smoke = rv.get("functional_smoke") or {}
    checks = gameplay_checks or {}

    window_opened = bool(
        obs.get("window_opened")
        or sig.get("window_opened")
        or any(
            a.get("smoke_result") in ("stable_window", "launch_ok")
            for a in (obs.get("artifact_analyses") or [])
            if isinstance(a, dict)
        )
        or obs.get("runtime_screenshots")
    )
    fps_detected = bool(
        sig.get("fps_detected")
        or (obs.get("metrics") or {}).get("fps_detected")
        or float(obs.get("runtime_duration_seconds") or 0) > 0
    )
    crash = bool(
        obs.get("crash_detected")
        or (rv.get("crash") or {}).get("crash_detected")
        or sig.get("crash") == "observed"
    )
    scene_loaded = bool(
        sig.get("scene_loaded")
        or sig.get("mentions_scene")
        or any(
            isinstance(u, dict) and u.get("scene_loaded_hint")
            for u in (obs.get("unity_observation_summary") or [])
        )
        or (checks.get("scene_transition") or {}).get("observed")
    )
    launch_attempted = obs.get("game_launch_attempted")
    if launch_attempted is None:
        launch_attempted = sig.get("game_launch_attempted")
    if launch_attempted is None and not is_structure_only_runtime(inv):
        launch_attempted = window_opened and smoke.get("functional_smoke_pass") is True

    return {
        "window_opened": window_opened,
        "fps_detected": fps_detected,
        "crash": crash,
        "scene_loaded": scene_loaded,
        "game_launch_attempted": bool(launch_attempted) if launch_attempted is not None else None,
        "runtime_method": _runtime_method(obs),
        "structure_only": is_structure_only_runtime(inv),
        "functional_smoke_pass": smoke.get("functional_smoke_pass"),
    }


def assess_playtest_evidence(
    artifact_inventory: Optional[Dict[str, Any]] = None,
    *,
    submission_paths: Optional[List[str]] = None,
    gameplay_checks: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Pearson PRO playtest paths (any one satisfies C.P6 / M3 / D2 / D3 gates):
      1. L5 human playtest
      2. Documented gameplay video inference
      3. Runtime + gameplay validation (engine-specific floor)
      4. Human review authority already recorded
    """
    inv = artifact_inventory or {}
    engine_id = detect_primary_game_engine(inv, submission_paths=submission_paths)
    policy = get_engine_policy(engine_id)
    checks = dict(gameplay_checks or {})
    obs = inv.get("runtime_observation_report") or {}

    gv = inv.get("gameplay_verification") or obs.get("gameplay_verification") or {}
    if not gv:
        for analysis in obs.get("artifact_analyses") or []:
            if isinstance(analysis, dict) and isinstance(analysis.get("gameplay_verification"), dict):
                gv = analysis["gameplay_verification"]
                break
    if gv:
        try:
            from app.gameplay_verifier import build_gameplay_checks_from_verification

            auto_checks = build_gameplay_checks_from_verification(gv)
            checks = {**auto_checks, **checks}
        except Exception:
            pass
    telemetry = build_runtime_telemetry(inv, gameplay_checks=checks)

    smoke = (inv.get("runtime_validation") or obs.get("runtime_validation") or {}).get(
        "functional_smoke"
    ) or {}
    try:
        from app.gameplay_verifier import _test_document_present, assess_automated_l4_gate

        automated_gate = assess_automated_l4_gate(
            gv,
            test_document_present=_test_document_present(inv),
            functional_smoke_pass=smoke.get("functional_smoke_pass") is True,
        )
    except Exception:
        automated_gate = {}

    l5 = inv.get("l5_human_playtest") or {}
    human_playtest = bool(
        obs.get("human_playtest_verified")
        or obs.get("manual_playtest_verified")
        or obs.get("interaction_visually_corroborated")
        or l5.get("verified")
        or l5.get("status") == "verified"
    )

    gvi = inv.get("gameplay_video_inference") or {}
    va = gvi.get("video_analysis") or {}
    gameplay_video_documented = bool(
        inv.get("gameplay_video_detected")
        or gvi.get("status") in ("analyzed", "completed", "partial")
        or va.get("runtime_hints")
        or va.get("scenes_detected")
    )

    mechanics_n = _count_core_mechanics(checks)
    min_mech = int(policy.get("min_core_mechanics_for_cp6") or 2)
    launch_ok = telemetry.get("game_launch_attempted") is True and not telemetry.get(
        "structure_only"
    )
    runtime_ok = (
        launch_ok
        and not telemetry.get("crash")
        and (
            telemetry.get("window_opened")
            or telemetry.get("scene_loaded")
        )
        and telemetry.get("functional_smoke_pass") is True
    )
    gameplay_floor = mechanics_n >= min_mech
    if engine_id == "gamemaker" and policy.get("human_review_required") and not gameplay_floor:
        runtime_gameplay_validated = False
    else:
        runtime_gameplay_validated = runtime_ok and (
            gameplay_floor or (engine_id == "unity" and bool(obs.get("unity_observation_summary")))
        )

    human_review_recorded = human_playtest or str(
        (inv.get("manual_playtest") or {}).get("status") or ""
    ).lower() in ("verified", "completed")

    paths = {
        "human_playtest": human_playtest,
        "gameplay_video_documented": gameplay_video_documented,
        "runtime_gameplay_validated": runtime_gameplay_validated,
        "human_review_recorded": human_review_recorded,
        "automated_l4_full": bool(automated_gate.get("l4_full")),
        "automated_l4_partial": bool(automated_gate.get("l4_partial")),
        "automated_l4_verified": bool(
            automated_gate.get("l4_full") or automated_gate.get("l4_partial")
        ),
    }
    if paths["automated_l4_full"]:
        paths["runtime_gameplay_validated"] = True
    # L4_partial is tracked for per-criterion gate decisions (P5 only) in
    # apply_runtime_evidence_gate — it must NOT satisfy the overall gate alone.
    any_path = any(
        (
            paths["human_playtest"],
            paths["gameplay_video_documented"],
            paths["runtime_gameplay_validated"],
            paths["human_review_recorded"],
            paths["automated_l4_full"],
        )
    )

    return {
        "version": GOVERNANCE_VERSION,
        "engine_id": engine_id,
        "engine_policy": policy,
        "playtest_paths": paths,
        "any_path_satisfied": any_path,
        "runtime_telemetry": telemetry,
        "core_mechanics_observed": mechanics_n,
        "min_core_mechanics_required": min_mech,
        "structure_only_runtime": telemetry.get("structure_only"),
        "automated_l4_gate": automated_gate,
        "summary_ar": _summary_ar(engine_id, policy, paths, telemetry, mechanics_n, min_mech),
    }


def _summary_ar(
    engine_id: str,
    policy: Dict[str, Any],
    paths: Dict[str, bool],
    telemetry: Dict[str, Any],
    mechanics_n: int,
    min_mech: int,
) -> str:
    eng_label = {
        "godot": "Godot",
        "unity": "Unity",
        "gamemaker": "GameMaker",
        "unreal": "Unreal Engine",
    }.get(engine_id, engine_id)
    if paths["human_playtest"]:
        return f"{eng_label}: playtest بشري (L5) موثّق."
    if paths["gameplay_video_documented"]:
        return f"{eng_label}: فيديو gameplay موثّق."
    if paths.get("automated_l4_verified"):
        return f"{eng_label}: تحقق L4 آلي (MenuNavigator + حركة/قفز/HUD)."
    if paths["runtime_gameplay_validated"]:
        return (
            f"{eng_label}: تحقق تشغيل + gameplay ({mechanics_n}/{min_mech} آليات أساسية)."
        )
    if telemetry.get("structure_only"):
        return (
            f"{eng_label}: فحص هيكلي/ملفات فقط (exe/pck/apk) — "
            "لا يكفي لـ C.P6/M/D في PRO."
        )
    if policy.get("human_review_required"):
        return (
            f"{eng_label}: يُفضّل مراجعة بشرية (L5) — "
            "أدوات التحليل الآلي محدودة."
        )
    return (
        f"{eng_label}: لا playtest موثّق — مطلوب تشغيل حقيقي أو L5 "
        f"({mechanics_n}/{min_mech} آليات)."
    )


def apply_pro_engine_gameplay_governance(
    criteria_results: List[Dict[str, Any]],
    artifact_inventory: Optional[Dict[str, Any]] = None,
    *,
    submission_paths: Optional[List[str]] = None,
    gameplay_checks: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Demote C.P6 / C.M3 / BC.D2 / BC.D3 when no Pearson playtest path is satisfied.
    Marks rows with ``pro_gameplay_governance_hold`` so finalizer cannot re-promote.
    """
    assessment = assess_playtest_evidence(
        artifact_inventory,
        submission_paths=submission_paths,
        gameplay_checks=gameplay_checks,
    )
    changes: List[str] = []
    automated_gate = assessment.get("automated_l4_gate") or {}
    criterion_pass = automated_gate.get("criterion_pass") or {}

    if assessment["any_path_satisfied"]:
        return changes, assessment

    engine_id = assessment["engine_id"]
    policy = assessment["engine_policy"]
    for row in criteria_results:
        if not isinstance(row, dict) or not row.get("achieved"):
            continue
        short = _short_level(str(row.get("criteria_level") or ""))
        if short not in _PLAYTEST_GATED_SHORT:
            continue
        if criterion_pass.get(short):
            continue

        if engine_id == "gamemaker" and policy.get("human_review_required"):
            reason = (
                "GameMaker PRO: لا يُمنح المعيار دون playtest بشري (L5) أو gameplay موثّق — "
                "التشغيل الآلي لا يكتشف حلقة اللعب بموثوقية كافية."
            )
            authority = "HUMAN_REVIEW_REQUIRED"
        elif short == "P6":
            reason = (
                "Pearson PRO: C.P6 يتطلب أحد: playtest حقيقي، فيديو gameplay، "
                "تحقق Runtime+Gameplay ناجح، أو مراجعة بشرية (L5). "
                "وجود exe/pck/apk/لقطات وحده لا يكفي."
            )
            authority = "HUMAN_REVIEW_REQUIRED"
        else:
            reason = (
                f"Pearson PRO: {row.get('criteria_level')} لا يُمنح دون إثبات اختبار/لعب "
                "(نفس بوابة C.P6 — playtest أو runtime+gameplay أو L5)."
            )
            authority = "RUNTIME_INSUFFICIENT"

        _demote_row(row, reason)
        row["achievement_authority"] = authority
        row["pro_gameplay_governance_hold"] = True
        row["engine_governance_engine"] = engine_id
        changes.append(f"{row.get('criteria_level')}:engine_playtest_gate")

    return changes, assessment


def build_engine_runtime_summary(
    artifact_inventory: Optional[Dict[str, Any]] = None,
    *,
    submission_paths: Optional[List[str]] = None,
    gameplay_checks: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Per-engine PRO audit block for IV pack / UI."""
    assessment = assess_playtest_evidence(
        artifact_inventory,
        submission_paths=submission_paths,
        gameplay_checks=gameplay_checks,
    )
    engine_id = assessment["engine_id"]
    policy = assessment["engine_policy"]
    return {
        "engine_id": engine_id,
        "policy": {
            "gameplay_validation_required": policy.get("gameplay_validation_required"),
            "unity_runtime_validation": policy.get("unity_runtime_validation"),
            "playtest_required": policy.get("playtest_required"),
            "human_review_required": policy.get("human_review_required"),
            "support_tier_ar": policy.get("support_tier_ar"),
        },
        "runtime_telemetry": assessment["runtime_telemetry"],
        "playtest_assessment": assessment,
        "pearson_rule_ar": (
            "C.P5: ملفات التنفيذ + التقرير قد تدعم الإنتاج؛ "
            "C.P6/M/D: لا تُمنح دون playtest أو gameplay validation أو L5."
        ),
    }
