"""
Stage 4.6 — Visual state classification (heuristic, advisory only).

Classifies runtime screenshots into coarse visual states without claiming gameplay verification.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


VISUAL_STATES = (
    "black_screen",
    "loading_screen",
    "main_menu_candidate",
    "gameplay_candidate",
    "static_ui",
    "unknown",
)


def _luma_variance(pixels: List[Tuple[int, int, int]]) -> float:
    if not pixels:
        return 0.0
    lumas = [(r + g + b) / 3.0 for r, g, b in pixels]
    avg = sum(lumas) / len(lumas)
    return sum((x - avg) ** 2 for x in lumas) / len(lumas)


def _approx_entropy(pixels: List[Tuple[int, int, int]], *, bins: int = 16) -> float:
    if not pixels:
        return 0.0
    counts = [0] * bins
    for r, g, b in pixels:
        bucket = min(bins - 1, int(((r + g + b) / 3.0) / 256.0 * bins))
        counts[bucket] += 1
    total = float(len(pixels))
    entropy = 0.0
    for count in counts:
        if count <= 0:
            continue
        p = count / total
        entropy -= p * math.log2(p)
    return round(entropy, 4)


def compute_extended_visual_stats(image: Any) -> Dict[str, Any]:
    """Extended stats for heuristic visual state classification."""
    rgb = image.convert("RGB")
    width, height = rgb.size
    sample = rgb.resize((64, 64))
    pixels = list(sample.getdata())
    extrema = rgb.getextrema()
    min_channel = min(int(pair[0]) for pair in extrema)
    max_channel = max(int(pair[1]) for pair in extrema)
    avg_luma = round(sum((r + g + b) / 3.0 for r, g, b in pixels) / len(pixels), 2)
    variance = round(_luma_variance(pixels), 2)
    entropy = _approx_entropy(pixels)
    dynamic_range = max_channel - min_channel

    # Center-band contrast hint for loading bars / menus
    center = sample.crop((16, 24, 48, 40))
    center_pixels = list(center.getdata())
    center_variance = round(_luma_variance(center_pixels), 2)

    return {
        "width": width,
        "height": height,
        "resolution": f"{width}x{height}",
        "avg_luma_approx": avg_luma,
        "min_channel": min_channel,
        "max_channel": max_channel,
        "dynamic_range": dynamic_range,
        "luma_variance": variance,
        "entropy_approx": entropy,
        "center_band_variance": center_variance,
        "black_screen_possible": max_channel <= 18,
        "window_visible": width > 0 and height > 0,
    }


def classify_visual_state(stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Heuristic coarse visual state — advisory only.
    """
    reasons: List[str] = []
    state = "unknown"
    confidence = 0.35

    avg = float(stats.get("avg_luma_approx") or 0)
    variance = float(stats.get("luma_variance") or 0)
    entropy = float(stats.get("entropy_approx") or 0)
    dynamic_range = float(stats.get("dynamic_range") or 0)
    center_var = float(stats.get("center_band_variance") or 0)
    black = stats.get("black_screen_possible") is True

    if black or (dynamic_range < 20 and avg < 25):
        state = "black_screen"
        confidence = 0.82 if black else 0.62
        reasons.append("low brightness and low dynamic range")
    elif avg < 90 and center_var < 120 and dynamic_range < 90:
        state = "loading_screen"
        confidence = 0.58
        reasons.append("muted palette with low center-band variance")
    elif variance < 900 and entropy < 2.4 and dynamic_range < 110:
        state = "static_ui"
        confidence = 0.55
        reasons.append("low variance static layout")
    elif center_var < 180 and entropy < 3.0 and dynamic_range < 140:
        state = "main_menu_candidate"
        confidence = 0.52
        reasons.append("center-weighted UI-like contrast pattern")
    elif variance >= 900 or entropy >= 3.0:
        state = "gameplay_candidate"
        confidence = 0.48
        reasons.append("higher visual complexity — gameplay not verified")
    else:
        state = "unknown"
        confidence = 0.35
        reasons.append("insufficient visual signal separation")

    return {
        "visual_state": state,
        "visual_state_confidence": round(confidence, 2),
        "classification_mode": "heuristic_v1",
        "classification_reasons": reasons,
        "authority_note_ar": (
            "visual_state استشاري — لا يثبت gameplay ولا menu interaction."
        ),
    }


def classify_visual_state_from_image(image: Any) -> Dict[str, Any]:
    stats = compute_extended_visual_stats(image)
    classification = classify_visual_state(stats)
    stats["black_screen_possible"] = classification["visual_state"] == "black_screen" or stats.get(
        "black_screen_possible"
    )
    return {
        "visual_stats": stats,
        **classification,
    }


def detect_visual_freeze(screenshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compare consecutive captured screenshots for near-identical frames.
    """
    captured = [s for s in screenshots if s.get("status") == "captured"]
    if len(captured) < 2:
        return {
            "freeze_possible": False,
            "compared_pairs": 0,
            "note_ar": "لا توجد لقطات كافية لمقارنة freeze.",
        }

    try:
        from PIL import Image  # type: ignore
    except Exception:
        return {
            "freeze_possible": False,
            "compared_pairs": 0,
            "note_ar": "Pillow unavailable for freeze comparison.",
        }

    similar_pairs = 0
    compared = 0
    for prev, nxt in zip(captured, captured[1:]):
        p_path = prev.get("path")
        n_path = nxt.get("path")
        if not p_path or not n_path:
            continue
        try:
            p_img = Image.open(p_path).convert("RGB").resize((32, 32))
            n_img = Image.open(n_path).convert("RGB").resize((32, 32))
            p_pixels = list(p_img.getdata())
            n_pixels = list(n_img.getdata())
            diff = sum(
                abs(int(a[i]) - int(b[i]))
                for a, b in zip(p_pixels, n_pixels)
                for i in range(min(len(a), len(b)))
            ) / (32 * 32 * 3)
            compared += 1
            if diff < 4.0:
                similar_pairs += 1
        except OSError:
            continue

    freeze_possible = compared > 0 and similar_pairs == compared
    return {
        "freeze_possible": freeze_possible,
        "compared_pairs": compared,
        "similar_pairs": similar_pairs,
        "note_ar": (
            "freeze_possible يعني frames متطابقة تقريباً — لا يثبت crash أو gameplay."
        ),
    }


def aggregate_visual_runtime_confidence(screenshots: List[Dict[str, Any]]) -> float:
    captured = [s for s in screenshots if s.get("status") == "captured"]
    if not captured:
        return 0.0
    scores: List[float] = []
    for shot in captured:
        conf = float(shot.get("visual_state_confidence") or 0.0)
        state = shot.get("visual_state") or "unknown"
        if state == "black_screen":
            scores.append(min(conf, 0.55))
        elif state in ("loading_screen", "main_menu_candidate", "static_ui"):
            scores.append(min(conf + 0.08, 0.72))
        elif state == "gameplay_candidate":
            scores.append(min(conf + 0.05, 0.65))
        else:
            scores.append(conf * 0.7)
    return round(sum(scores) / len(scores), 2)


def build_visual_audit_summary(screenshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    captured = [s for s in screenshots if s.get("status") == "captured"]
    states = sorted({s.get("visual_state") for s in captured if s.get("visual_state")})
    observed_elements: List[str] = []
    if any(s.get("visual_state") == "black_screen" for s in captured):
        observed_elements.append("possible_black_screen")
    if any(s.get("visual_state") == "loading_screen" for s in captured):
        observed_elements.append("loading_like_surface")
    if any(s.get("visual_state") == "main_menu_candidate" for s in captured):
        observed_elements.append("menu_like_surface")
    if any(s.get("visual_state") == "gameplay_candidate" for s in captured):
        observed_elements.append("complex_visual_surface")
    if captured:
        observed_elements.append("rendered_output_captured")

    freeze = detect_visual_freeze(screenshots)
    return {
        "observed_visual_elements": observed_elements,
        "unverified_gameplay": [
            "player_input_response",
            "score_system",
            "collision_events",
            "win_loss_flow",
            "level_progression",
        ],
        "human_validation_required": [
            "gameplay_correctness",
            "criterion_achievement",
            "menu_to_gameplay_transition",
        ],
        "visual_states_observed": states,
        "visual_runtime_confidence": aggregate_visual_runtime_confidence(screenshots),
        "freeze_detection": freeze,
    }
