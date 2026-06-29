"""
Deterministic runtime ↔ detected-system corroboration (no LLM).

Links systems_semantic / systems_detected to aggregated runtime log signals and
screenshot path/name heuristics. Produces audit-friendly strength labels and
missing-runtime flags — informational only; does not affect grading verdicts.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

CORROBORATION_ENGINE_VERSION = "1.4"

# Deterministic modality weights (informational — not used for final achieved/grade).
_MODALITY_WEIGHTS: Mapping[str, float] = {
    "code_system": 0.4,
    "runtime_log": 0.3,
    "runtime_screenshot": 0.2,
    "video_frame": 0.1,
    "ocr_text": 0.1,
}

# Ordinal tiers for explainability (not grading).
_MODALITY_CONFIDENCE_TIER: Mapping[str, str] = {
    "code_system": "high",
    "runtime_log": "medium",
    "runtime_screenshot": "low",
    "video_frame": "low",
    "ocr_text": "low",
}

# Stable log signal → audit reason token (deterministic).
_LOG_SIGNAL_TO_REASON: Mapping[str, str] = {
    "mentions_collision": "runtime_log_contains_collision_keywords",
    "mentions_physics": "runtime_log_contains_physics_keywords",
    "mentions_ui": "runtime_log_contains_ui_keywords",
    "mentions_scene": "runtime_log_contains_scene_keywords",
    "mentions_save": "runtime_log_contains_save_keywords",
    "mentions_audio": "runtime_log_contains_audio_keywords",
    "mentions_animation": "runtime_log_contains_animation_keywords",
    "mentions_ai": "runtime_log_contains_ai_keywords",
    "mentions_input": "runtime_log_contains_input_keywords",
    "mentions_inventory": "runtime_log_contains_inventory_keywords",
}

# Per detected system: which aggregated log keys (ANY) count as corroboration,
# and which substrings (path or basename, lowercased) suggest relevant screenshots.
_SYSTEM_CORROB_RULES: Mapping[str, Mapping[str, Any]] = {
    "collision_system": {
        "log_any": ("mentions_collision",),
        "screenshot_tokens": (
            "collision",
            "trigger",
            "oncollision",
            "hit",
            "impact",
            "physics",
            "rigid",
        ),
    },
    "physics_system": {
        "log_any": ("mentions_physics", "mentions_collision"),
        "screenshot_tokens": ("physics", "gravity", "rigid", "force", "velocity", "addforce"),
    },
    "ui_system": {
        "log_any": ("mentions_ui",),
        "screenshot_tokens": ("ui", "hud", "menu", "canvas", "button", "interface", "healthbar"),
    },
    "scene_flow": {
        "log_any": ("mentions_scene",),
        "screenshot_tokens": ("scene", "level", "map", "world", "loading", "menu"),
    },
    "save_system": {
        "log_any": ("mentions_save",),
        "screenshot_tokens": ("save", "load", "checkpoint", "menu"),
    },
    "audio_system": {
        "log_any": ("mentions_audio",),
        "screenshot_tokens": ("audio", "sound", "music", "sfx", "volume"),
    },
    "animation_system": {
        "log_any": ("mentions_animation",),
        "screenshot_tokens": ("anim", "sprite", "character", "walk", "idle"),
    },
    "enemy_ai": {
        "log_any": ("mentions_ai",),
        "screenshot_tokens": ("enemy", "ai", "patrol", "nav", "boss", "npc"),
    },
    "input_system": {
        "log_any": ("mentions_input",),
        "screenshot_tokens": ("input", "control", "keyboard", "keybind", "touch"),
    },
    "inventory_system": {
        "log_any": ("mentions_inventory",),
        "screenshot_tokens": ("inventory", "item", "hotbar", "loot", "pickup"),
    },
}


def _execution_bonus(tier: Optional[str]) -> float:
    t = (tier or "unknown").strip().lower()
    if t == "strong":
        return 0.10
    if t == "medium":
        return 0.07
    if t == "weak":
        return 0.04
    return 0.0


def _semantic_execution_by_system(profile: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    if not profile:
        return {}
    us = profile.get("unity_semantic") or {}
    if not isinstance(us, dict) or "error" in us:
        return {}
    out: Dict[str, str] = {}
    for d in us.get("system_detections") or []:
        if not isinstance(d, dict):
            continue
        sy = d.get("system")
        if not sy:
            continue
        out[str(sy)] = str(d.get("execution_evidence") or "unknown")
    return out


def _aggregate_log_signals(runtime_evidence: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """OR-merge boolean log signal flags across all parsed log files."""
    if not runtime_evidence or not isinstance(runtime_evidence, dict):
        return {}
    merged: Dict[str, bool] = {}
    for row in runtime_evidence.get("log_files") or []:
        if not isinstance(row, dict):
            continue
        sig = row.get("signals") or {}
        if not isinstance(sig, dict):
            continue
        for k, v in sig.items():
            if not k.startswith("mentions_") or not isinstance(v, bool):
                continue
            merged[k] = merged.get(k, False) or v
    return merged


def _log_lines_total(runtime_evidence: Optional[Mapping[str, Any]]) -> int:
    """Sum of line_count from parsed runtime logs (0 if none)."""
    if not runtime_evidence or not isinstance(runtime_evidence, dict):
        return 0
    total = 0
    for row in runtime_evidence.get("log_files") or []:
        if not isinstance(row, dict):
            continue
        sig = row.get("signals") or {}
        if not isinstance(sig, dict):
            continue
        try:
            total += int(sig.get("line_count") or 0)
        except (TypeError, ValueError):
            continue
    return total


def _dedupe_preserve_order(items: Sequence[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for x in items:
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _reasoning_code(profile: Optional[Mapping[str, Any]], system: str) -> List[str]:
    out: List[str] = []
    if not _code_modality_present(profile, system):
        return out
    out.append("code_system_detected")
    if system in _systems_from_semantic(profile):
        out.append("code_detection_source_unity_extractor")
    elif profile:
        for s in profile.get("systems_detected") or []:
            if s and str(s) == system:
                out.append("code_detection_source_project_pattern_sample")
                break
    return out


def _reasoning_log(log_any: Tuple[Any, ...], agg: Mapping[str, Any]) -> List[str]:
    out: List[str] = []
    for k in log_any:
        key = str(k)
        if bool(agg.get(key)):
            reason = _LOG_SIGNAL_TO_REASON.get(key, f"runtime_log_keyword_{key}")
            out.append(reason)
    return out


def _reasoning_screenshot(system: str, runtime_screenshot_count: int) -> List[str]:
    if runtime_screenshot_count <= 0:
        return []
    return [f"runtime_screenshot_filename_matches_{system}"]


def _reasoning_video(video_frame_count: int) -> List[str]:
    if video_frame_count <= 0:
        return []
    return ["runtime_video_frames_extracted"]


def _reasoning_ocr(ocr_item_count: int) -> List[str]:
    if ocr_item_count <= 0:
        return []
    return ["ocr_text_extracted_from_runtime_visuals"]


def _video_frame_global(profile: Optional[Mapping[str, Any]]) -> int:
    if not profile:
        return 0
    rt = profile.get("runtime_evidence") or {}
    if not isinstance(rt, dict):
        return 0
    try:
        return max(0, int(rt.get("video_frame_count") or 0))
    except (TypeError, ValueError):
        return 0


def _ocr_item_global(profile: Optional[Mapping[str, Any]]) -> int:
    if not profile:
        return 0
    rt = profile.get("runtime_evidence") or {}
    if not isinstance(rt, dict):
        return 0
    items = rt.get("ocr_evidence_items") or []
    if not isinstance(items, list):
        return 0
    return sum(1 for x in items if isinstance(x, dict) and x.get("evidence_type") == "ocr_text")


def _modality_tiers_present(modalities: Sequence[str]) -> Dict[str, str]:
    return {m: _MODALITY_CONFIDENCE_TIER.get(m, "unknown") for m in modalities if m in _MODALITY_CONFIDENCE_TIER}


def _runtime_source_confidence_tier(
    runtime_corroborated: bool,
    log_signal_present: bool,
    runtime_screenshot_count: int,
    video_frame_count: int,
) -> str:
    if not runtime_corroborated:
        return "none"
    if log_signal_present:
        return "medium"
    if runtime_screenshot_count > 0 or video_frame_count > 0:
        return "low"
    return "none"


def _noise_flags_for_system(
    profile: Optional[Mapping[str, Any]],
    system: str,
    log_signal_present: bool,
    runtime_screenshot_count: int,
    runtime_corroborated: bool,
    log_lines_total: int,
    video_frame_global: int,
) -> List[Dict[str, str]]:
    flags: List[Dict[str, str]] = []
    if (
        runtime_corroborated
        and runtime_screenshot_count > 0
        and not log_signal_present
    ):
        flags.append({"flag": "screenshot_filename_match_only"})
    if log_signal_present and log_lines_total < 3:
        flags.append({"flag": "runtime_log_keyword_without_context"})
    if profile and _code_modality_present(profile, system):
        if system not in _systems_from_semantic(profile):
            # Pattern-only code signal (weaker than extractor row)
            flags.append({"flag": "pattern_hint_code_signal"})
    if (
        video_frame_global > 0
        and not log_signal_present
        and runtime_screenshot_count == 0
    ):
        flags.append({"flag": "video_frames_extracted_without_runtime_linkage"})
    return flags


def _build_explainable_fields(
    profile: Optional[Mapping[str, Any]],
    system: str,
    rule: Mapping[str, Any],
    agg: Mapping[str, Any],
    log_signal_present: bool,
    runtime_screenshot_count: int,
    runtime_corroborated: bool,
    modalities: Sequence[str],
    log_lines_total: int,
    video_frame_global: int,
    ocr_item_global: int,
) -> Dict[str, Any]:
    log_any = tuple(rule.get("log_any") or ())
    log_reasons = sorted(_reasoning_log(log_any, agg))
    reasoning = _dedupe_preserve_order(
        list(_reasoning_code(profile, system))
        + log_reasons
        + _reasoning_screenshot(system, runtime_screenshot_count)
        + _reasoning_video(video_frame_global)
        + _reasoning_ocr(ocr_item_global)
    )
    noise = _noise_flags_for_system(
        profile,
        system,
        log_signal_present,
        runtime_screenshot_count,
        runtime_corroborated,
        log_lines_total,
        video_frame_global,
    )
    modality_tiers = _modality_tiers_present(modalities)
    src_tier = _runtime_source_confidence_tier(
        runtime_corroborated,
        log_signal_present,
        runtime_screenshot_count,
        video_frame_global,
    )
    return {
        "corroboration_reasoning": reasoning,
        "corroboration_noise_flags": noise,
        "modality_confidence_tiers": modality_tiers,
        "source_confidence_tier": src_tier,
    }


def _systems_from_semantic(profile: Optional[Mapping[str, Any]]) -> Set[str]:
    out: Set[str] = set()
    if not profile:
        return out
    for d in profile.get("systems_semantic") or []:
        if isinstance(d, dict) and d.get("system"):
            out.add(str(d["system"]))
    return out


def _code_modality_present(profile: Optional[Mapping[str, Any]], system: str) -> bool:
    """Code-side detection (Unity semantic row and/or pattern tag)."""
    if system in _systems_from_semantic(profile):
        return True
    for s in profile.get("systems_detected") or []:
        if s and str(s) == system:
            return True
    return False


def _mention_to_systems() -> Mapping[str, Tuple[str, ...]]:
    """Aggregate log signal key → systems that treat it as corroborating log evidence."""
    rev: Dict[str, List[str]] = {}
    for sys_name, rule in _SYSTEM_CORROB_RULES.items():
        for k in rule.get("log_any") or ():
            rev.setdefault(str(k), []).append(sys_name)
    return {k: tuple(sorted(set(v))) for k, v in rev.items()}


_MENTION_TO_SYSTEMS: Mapping[str, Tuple[str, ...]] = _mention_to_systems()


def _has_runtime_log_files(runtime_evidence: Optional[Mapping[str, Any]]) -> bool:
    if not runtime_evidence or not isinstance(runtime_evidence, dict):
        return False
    return bool(runtime_evidence.get("log_files"))


def _detected_systems_union(profile: Optional[Mapping[str, Any]]) -> Set[str]:
    out: Set[str] = set()
    if not profile:
        return out
    for d in profile.get("systems_semantic") or []:
        if isinstance(d, dict) and d.get("system"):
            out.add(str(d["system"]))
    for s in profile.get("systems_detected") or []:
        if s:
            out.add(str(s))
    return out


def _screenshot_rows(runtime_evidence: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    if not runtime_evidence or not isinstance(runtime_evidence, dict):
        return []
    rows = runtime_evidence.get("screenshot_candidates") or []
    return [r for r in rows if isinstance(r, dict)]


def _count_matching_screenshots(screenshots: Sequence[Mapping[str, Any]], tokens: Tuple[str, ...]) -> int:
    n = 0
    for row in screenshots:
        p = str(row.get("path") or "").lower()
        b = str(row.get("basename") or "").lower()
        blob = f"{p}\n{b}"
        if any(tok in blob for tok in tokens):
            n += 1
    return n


def _corroboration_confidence(
    log_signal_present: bool,
    runtime_screenshot_count: int,
    video_frame_count: int,
    exec_tier: Optional[str],
) -> float:
    score = 0.0
    if log_signal_present:
        score += 0.42
    # Cap visual contribution so screenshots alone rarely reach "medium"
    score += min(runtime_screenshot_count, 3) * 0.14
    score += min(video_frame_count, 3) * 0.05
    score += _execution_bonus(exec_tier)
    return round(min(1.0, score), 4)


def _strength_from(
    log_signal_present: bool,
    runtime_screenshot_count: int,
    video_frame_count: int,
    confidence: float,
) -> str:
    if not log_signal_present and runtime_screenshot_count == 0 and video_frame_count == 0:
        return "none"
    if confidence >= 0.48:
        return "medium"
    return "weak"


def _build_modalities_and_scores(
    profile: Optional[Mapping[str, Any]],
    system: str,
    log_signal_present: bool,
    runtime_screenshot_count: int,
    video_frame_count: int,
    ocr_item_count: int,
) -> Tuple[List[str], float, float]:
    modalities: List[str] = []
    if _code_modality_present(profile, system):
        modalities.append("code_system")
    if log_signal_present:
        modalities.append("runtime_log")
    if runtime_screenshot_count > 0:
        modalities.append("runtime_screenshot")
    if video_frame_count > 0:
        modalities.append("video_frame")
    if ocr_item_count > 0:
        modalities.append("ocr_text")
    diversity = round(len(modalities) / 3.0, 4)
    weighted = round(
        sum(_MODALITY_WEIGHTS[m] for m in modalities if m in _MODALITY_WEIGHTS),
        4,
    )
    return modalities, diversity, weighted


def build_runtime_corroboration(profile: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """
    Build runtime corroboration summary from project profile only (deterministic).

    Does not read raw source outside profile.runtime_evidence and unity semantic.
    """
    if not profile:
        return {
            "engine_version": CORROBORATION_ENGINE_VERSION,
            "by_system": {},
            "missing_runtime_corroboration_flags": [],
            "corroboration_conflicts": [],
            "aggregate_log_signals": {},
            "evidence_weights": dict(_MODALITY_WEIGHTS),
            "modality_confidence_tier_reference": dict(_MODALITY_CONFIDENCE_TIER),
        }

    detected = _detected_systems_union(profile)
    agg = _aggregate_log_signals(profile.get("runtime_evidence"))
    log_lines_total = _log_lines_total(profile.get("runtime_evidence"))
    exec_map = _semantic_execution_by_system(profile)
    screenshots = _screenshot_rows(profile.get("runtime_evidence"))
    video_g = _video_frame_global(profile)
    ocr_g = _ocr_item_global(profile)

    by_system: Dict[str, Any] = {}
    flags: List[Dict[str, str]] = []
    conflicts: List[Dict[str, Any]] = []

    for system in sorted(detected):
        rule = _SYSTEM_CORROB_RULES.get(system)
        if not rule:
            continue
        log_any = rule.get("log_any") or ()
        tokens = tuple(rule.get("screenshot_tokens") or ())
        log_signal_present = any(bool(agg.get(k)) for k in log_any)
        runtime_screenshot_count = _count_matching_screenshots(screenshots, tokens)
        exec_tier = exec_map.get(system)
        confidence = _corroboration_confidence(
            log_signal_present, runtime_screenshot_count, video_g, exec_tier
        )
        strength = _strength_from(
            log_signal_present, runtime_screenshot_count, video_g, confidence
        )
        runtime_corroborated = (
            log_signal_present or runtime_screenshot_count > 0 or video_g > 0
        )
        modalities, modality_diversity_score, weighted_corroboration_score = _build_modalities_and_scores(
            profile, system, log_signal_present, runtime_screenshot_count, video_g, ocr_g
        )
        explain = _build_explainable_fields(
            profile,
            system,
            rule,
            agg,
            log_signal_present,
            runtime_screenshot_count,
            runtime_corroborated,
            modalities,
            log_lines_total,
            video_g,
            ocr_g,
        )

        by_system[system] = {
            "runtime_corroborated": runtime_corroborated,
            "log_signal_present": log_signal_present,
            "runtime_screenshot_count": runtime_screenshot_count,
            "corroboration_confidence": confidence,
            "corroboration_strength": strength,
            "corroboration_modalities": modalities,
            "modality_diversity_score": modality_diversity_score,
            "weighted_corroboration_score": weighted_corroboration_score,
            "evidence_weights_applied": dict(_MODALITY_WEIGHTS),
            **explain,
        }
        if strength == "none":
            flags.append(
                {
                    "flag": f"{system}_detected_without_runtime_signal",
                    "system": system,
                }
            )
            conflicts.append(
                {
                    "flag": "system_detected_without_any_runtime_artifact",
                    "system": system,
                }
            )

    # Log signals that do not align with any code-detected system in this profile.
    for mkey, active in sorted(agg.items()):
        if not active or not str(mkey).startswith("mentions_"):
            continue
        candidates = _MENTION_TO_SYSTEMS.get(str(mkey), ())
        if not candidates:
            continue
        if not set(candidates) & detected:
            conflicts.append(
                {
                    "flag": "runtime_log_present_without_matching_system",
                    "mention_key": str(mkey),
                    "candidate_systems": list(candidates),
                }
            )

    if _has_runtime_log_files(profile.get("runtime_evidence")) and not any(
        bool(v) for v in agg.values() if isinstance(v, bool)
    ):
        conflicts.append(
            {
                "flag": "runtime_log_present_without_matching_system",
                "detail": "log_files_present_but_no_keyword_signals",
            }
        )

    return {
        "engine_version": CORROBORATION_ENGINE_VERSION,
        "by_system": by_system,
        "missing_runtime_corroboration_flags": flags,
        "corroboration_conflicts": conflicts,
        "aggregate_log_signals": dict(sorted(agg.items())),
        "evidence_weights": dict(_MODALITY_WEIGHTS),
        "modality_confidence_tier_reference": dict(_MODALITY_CONFIDENCE_TIER),
    }
