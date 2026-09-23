"""
Deterministic GameMaker mechanics analyzer — static GML/YY evidence.

Scans .gml event files + .yy/.yyp metadata and produces a stable,
evidence-backed report of which gameplay mechanics the student implemented
(movement, jump, score, lives/health, timer, win/lose, collision, ...).

Design goals:
  1. 100% deterministic — same submission bytes → identical output, every run.
  2. Evidence-based — every detected mechanic carries file:line proof lines.
  3. No AI calls, no runtime dependency — works on any OS (Windows/Linux).

This is the authoritative evidence layer for "هل أضاف الطالب المطلوب"
(timer/lives/score/…) in GameMaker submissions. Runtime observation may
corroborate it but can never contradict or randomize it.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern, Tuple

MECHANICS_VERSION = "gamemaker_gml_mechanics_v1"

_MAX_FILES = 400
_MAX_FILE_BYTES = 512_000
_MAX_EVIDENCE_PER_MECHANIC = 8

# Each mechanic: (id, arabic label, [(pattern, note)], needs_all=False)
# Patterns run per-line, case-insensitive, against GML source.
_MECHANIC_PATTERNS: Tuple[Tuple[str, str, Tuple[Tuple[str, str], ...]], ...] = (
    (
        "player_movement",
        "حركة اللاعب",
        (
            (r"\bkeyboard_check(?:_pressed|_released)?\s*\(\s*vk_(left|right|up|down)\b", "arrow-key movement"),
            (r"\bkeyboard_check(?:_pressed|_released)?\s*\(\s*ord\s*\(\s*[\"'][WASD][\"']\s*\)", "WASD movement"),
            (r"\b(hspeed|vspeed|hsp|vsp)\s*[+\-]?=", "speed variable updated"),
            (r"\bx\s*[+\-]=\s*", "x position updated"),
            (r"\bmove_(and_collide|towards_point|wrap)\s*\(", "movement function"),
            (r"\bmotion_(set|add)\s*\(", "motion function"),
        ),
    ),
    (
        "player_jump",
        "القفز",
        (
            (r"\bkeyboard_check(?:_pressed)?\s*\(\s*vk_space\b", "space key jump"),
            (r"\bgravity\s*=", "gravity set"),
            (r"\bgrav\b\s*[+\-]?=", "custom gravity variable"),
            (r"\bplace_meeting\s*\(\s*x\s*,\s*y\s*\+\s*1", "ground check (place_meeting)"),
            (r"\b(vspeed|vsp)\s*=\s*-", "upward impulse"),
        ),
    ),
    (
        "score_system",
        "نظام النقاط",
        (
            (r"\bscore\s*[+\-]?=", "score variable updated"),
            (r"\bpoints?\s*[+\-]=", "points variable updated"),
            (r"\bdraw_text\s*\([^)]*score", "score drawn on screen"),
            (r"\bhighscore\b", "highscore referenced"),
        ),
    ),
    (
        "lives_system",
        "نظام الأرواح",
        (
            (r"\blives\s*[+\-]?=", "lives variable updated"),
            (r"\blives\s*[<>=!]", "lives compared"),
            (r"\bdraw_text\s*\([^)]*lives", "lives drawn on screen"),
            (r"\b(hearts?|arwah)\s*[+\-]=", "hearts variable updated"),
            (r"\bdraw_healthbar\s*\(", "healthbar drawn"),
        ),
    ),
    (
        "health_system",
        "نظام الصحة",
        (
            (r"\bhealth\s*[+\-]?=", "health variable updated"),
            (r"\bhealth\s*[<>=!]", "health compared"),
            (r"\b(hp|myhealth|player_health)\s*[+\-]=", "custom health variable"),
            (r"\bdraw_healthbar\s*\(", "healthbar drawn"),
        ),
    ),
    (
        "timer_system",
        "نظام الوقت/المؤقت",
        (
            (r"\balarm\s*\[\s*\d+\s*\]\s*=", "alarm timer set"),
            (r"\b(timer|time_left|countdown|game_time|counter)\s*[+\-]?=", "timer variable updated"),
            (r"\bdraw_text\s*\([^)]*\b(timer|time|countdown)", "timer drawn on screen"),
            (r"\broom_speed\b", "room_speed based timing"),
            (r"\bcurrent_time\b", "current_time used"),
            (r"\bdelta_time\b", "delta_time used"),
        ),
    ),
    (
        "collision",
        "التصادم",
        (
            (r"\bplace_meeting\s*\(", "place_meeting collision"),
            (r"\binstance_place\s*\(", "instance_place collision"),
            (r"\bcollision_(rectangle|circle|line|point)\s*\(", "collision function"),
            (r"\binstance_destroy\s*\(", "instance destroyed"),
        ),
    ),
    (
        "win_condition",
        "شرط الفوز",
        (
            (r"\broom_goto(?:_next)?\s*\(", "room transition (win/next level)"),
            (r"\b(win|victory|you_win|winner)\b", "win token in code"),
            (r"\bdraw_text\s*\([^)]*\b(win|victory)", "win text drawn"),
        ),
    ),
    (
        "lose_condition",
        "شرط الخسارة",
        (
            (r"\bgame_restart\s*\(", "game restart on loss"),
            (r"\broom_restart\s*\(", "room restart on loss"),
            (r"\bgame_end\s*\(", "game end"),
            (r"\b(game_?over|lose|dead|death)\b", "lose token in code"),
            (r"\bshow_message\s*\([^)]*\b(lose|over|خسر)", "lose message"),
        ),
    ),
    (
        "restart_flow",
        "إعادة التشغيل",
        (
            (r"\bgame_restart\s*\(", "game_restart called"),
            (r"\broom_restart\s*\(", "room_restart called"),
            (r"\bkeyboard_check(?:_pressed)?\s*\([^)]*\b(vk_enter|ord\s*\(\s*[\"']R[\"']\s*\))", "restart key"),
        ),
    ),
    (
        "menu_ui",
        "القائمة/الواجهة",
        (
            (r"\broom_goto\s*\(\s*\w*(menu|start|title)", "menu room transition"),
            (r"\bdraw_text\s*\([^)]*\b(start|play|menu)", "menu text drawn"),
        ),
    ),
    (
        "sound",
        "الصوت",
        (
            (r"\baudio_play_sound\s*\(", "audio_play_sound called"),
            (r"\bsound_play\s*\(", "sound_play called (legacy)"),
        ),
    ),
    (
        "enemy_interaction",
        "تفاعل العدو",
        (
            (r"\bobj?_?(enemy|monster|zombie|boss)\b", "enemy object referenced"),
            (r"\b(enemy|monster)\w*\s*[+\-.=]", "enemy variable"),
        ),
    ),
    (
        "collect_items",
        "جمع العناصر",
        (
            (r"\bobj?_?(coin|gem|star|apple|collect|pickup|key)\b", "collectible object referenced"),
        ),
    ),
)

# Event-file name → mechanic hints (deterministic filesystem evidence)
_EVENT_FILE_HINTS: Tuple[Tuple[Pattern[str], str, str], ...] = (
    (re.compile(r"^alarm_\d+\.gml$", re.I), "timer_system", "Alarm event file"),
    (re.compile(r"^collision_.*\.gml$", re.I), "collision", "Collision event file"),
    (re.compile(r"^keyboard_.*\.gml$", re.I), "player_movement", "Keyboard event file"),
    (re.compile(r"^keypress_.*\.gml$", re.I), "player_movement", "KeyPress event file"),
)


def _iter_gml_files(root: Path) -> List[Path]:
    """Stable sorted list of GML files under root."""
    files: List[Path] = []
    try:
        for fp in root.rglob("*.gml"):
            if any(part.startswith(".") for part in fp.parts):
                continue
            files.append(fp)
            if len(files) >= _MAX_FILES:
                break
    except OSError:
        pass
    # Deterministic order regardless of filesystem enumeration order.
    return sorted(files, key=lambda p: str(p).lower())


def _read_lines(fp: Path) -> List[str]:
    try:
        if fp.stat().st_size > _MAX_FILE_BYTES:
            return []
        return fp.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _room_count(project_root: Path) -> int:
    rooms = project_root / "rooms"
    if not rooms.is_dir():
        return 0
    try:
        return sum(1 for d in sorted(rooms.iterdir()) if d.is_dir())
    except OSError:
        return 0


def analyze_gml_mechanics(
    project_root: Optional[Path],
    *,
    gml_files: Optional[List[Path]] = None,
) -> Dict[str, Any]:
    """
    Deterministic mechanics report with per-mechanic evidence.

    Returns:
      {
        "version": ...,
        "mechanics": {mech_id: {"detected": bool, "label_ar": str,
                                "evidence": [{"file","line","snippet","note"}]}},
        "detected_ids": [...],           # sorted
        "signals": {...},                # runtime_signal_graph-compatible hints
        "gml_files_scanned": int,
        "deterministic": True,
      }
    """
    compiled = [
        (mech_id, label_ar, [(re.compile(pat, re.I), note) for pat, note in pats])
        for mech_id, label_ar, pats in _MECHANIC_PATTERNS
    ]
    mechanics: Dict[str, Dict[str, Any]] = {
        mech_id: {"detected": False, "label_ar": label_ar, "evidence": []}
        for mech_id, label_ar, _ in compiled
    }

    files = gml_files if gml_files is not None else (
        _iter_gml_files(project_root) if project_root else []
    )
    files = sorted({fp.resolve() for fp in files if fp.is_file()}, key=lambda p: str(p).lower())

    scanned = 0
    for fp in files[:_MAX_FILES]:
        lines = _read_lines(fp)
        if not lines:
            continue
        scanned += 1
        rel_name = fp.name
        # Filename-based event hints (Alarm_0.gml → timer, Collision_*.gml → collision)
        for hint_re, mech_id, note in _EVENT_FILE_HINTS:
            if hint_re.match(rel_name):
                bucket = mechanics[mech_id]
                if len(bucket["evidence"]) < _MAX_EVIDENCE_PER_MECHANIC:
                    bucket["evidence"].append(
                        {"file": str(fp), "line": 0, "snippet": rel_name, "note": note}
                    )
                bucket["detected"] = True
        for lineno, raw in enumerate(lines, start=1):
            line = raw.strip()
            if not line or line.startswith("//"):
                continue
            for mech_id, _label, pats in compiled:
                bucket = mechanics[mech_id]
                if len(bucket["evidence"]) >= _MAX_EVIDENCE_PER_MECHANIC:
                    continue
                for creg, note in pats:
                    if creg.search(line):
                        bucket["detected"] = True
                        bucket["evidence"].append(
                            {
                                "file": str(fp),
                                "line": lineno,
                                "snippet": line[:160],
                                "note": note,
                            }
                        )
                        break

    # Level progression evidence from room count (deterministic).
    if project_root:
        rooms = _room_count(project_root)
        if rooms >= 2:
            mechanics.setdefault(
                "level_progression",
                {"detected": False, "label_ar": "تعدد المستويات", "evidence": []},
            )
            mechanics["level_progression"]["detected"] = True
            mechanics["level_progression"]["evidence"].append(
                {
                    "file": str(project_root / "rooms"),
                    "line": 0,
                    "snippet": f"{rooms} rooms",
                    "note": "multiple rooms present",
                }
            )

    detected_ids = sorted(m for m, row in mechanics.items() if row["detected"])

    lives_or_health = ("lives_system" in detected_ids) or ("health_system" in detected_ids)
    signals: Dict[str, Any] = {}
    if "player_movement" in detected_ids:
        signals["player_movement_implemented"] = "static_detected"
    if "score_system" in detected_ids:
        signals["score_system_implemented"] = "static_detected"
    if lives_or_health:
        signals["lives_system_implemented"] = "static_detected"
    if "timer_system" in detected_ids:
        signals["timer_system_implemented"] = "static_detected"
    if "win_condition" in detected_ids or "lose_condition" in detected_ids:
        signals["win_lose_implemented"] = "static_detected"
    if "collision" in detected_ids:
        signals["collision_implemented"] = "static_detected"

    findings_ar: List[str] = []
    for mech_id in detected_ids:
        row = mechanics[mech_id]
        n = len(row["evidence"])
        findings_ar.append(f"تم رصد {row['label_ar']} في كود GML ({n} دليل)")

    return {
        "version": MECHANICS_VERSION,
        "mechanics": mechanics,
        "detected_ids": detected_ids,
        "signals": signals,
        "findings_ar": findings_ar,
        "gml_files_scanned": scanned,
        "deterministic": True,
        "authority_note_ar": (
            "أدلة ثابتة من كود GML — حتمية 100% وقابلة للتدقيق (ملف:سطر). "
            "التشغيل الفعلي يعززها ولا يلغيها."
        ),
    }
