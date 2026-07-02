"""Reject runtime screenshots that are not from the game window."""
from __future__ import annotations

from typing import Any, Dict, List


def validate_runtime_screenshot_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mark invalid captures as ``rejected`` so UI/runtime packages do not treat
    desktop/browser shots as gameplay evidence.
    """
    out = dict(record or {})
    if out.get("status") != "captured":
        return out

    reasons: List[str] = []
    scope = str(out.get("capture_scope") or "")
    if scope != "game_window":
        reasons.append(f"capture_scope:{scope or 'unknown'}")
    if not out.get("game_window_detected"):
        reasons.append("game_window_not_detected")
    visual = str(out.get("visual_state") or "")
    if visual in ("static_ui", "main_menu_candidate") and scope != "game_window":
        reasons.append("browser_or_desktop_surface")

    if reasons:
        out["status"] = "rejected"
        out["rejection_reasons"] = reasons
        out["gameplay_evidence"] = False
        out["authority_note_ar"] = (
            "لقطة مرفوضة — ليست من نافذة اللعبة (متصفح/سطح مكتب/شاشة تحميل)."
        )
    else:
        out["gameplay_evidence"] = True
    return out


def filter_gameplay_screenshots(screenshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    validated = [validate_runtime_screenshot_record(s) for s in screenshots if isinstance(s, dict)]
    return [s for s in validated if s.get("status") == "captured" and s.get("gameplay_evidence")]
