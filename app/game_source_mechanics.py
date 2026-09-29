"""
Multi-engine deterministic source-code mechanics analyzer.

Used as the *second* verification layer of the game grading policy:

    1. Run the game (.exe — supplied or temporarily built) and verify each
       required mechanic at runtime (movement, jump, score, ...).
    2. For every requirement the runtime could NOT confirm, open the source
       code and check whether the mechanic is actually implemented.

Supported languages: GameMaker GML (delegates to the existing analyzer),
Godot GDScript, Unity C#, Python/pygame, JavaScript/TypeScript (Phaser etc.).

Design rules:
  * Deterministic — no AI calls, same bytes -> same output.
  * Evidence based — each detection carries file:line snippets.
  * Conservative — a mechanic is "detected" only with at least one STRONG
    signal (e.g. jump key + upward velocity), or two distinct WEAK signals.
    Gravity alone is NOT a jump; any `x += 1` alone is NOT player movement.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Pattern, Sequence, Tuple

SOURCE_MECHANICS_VERSION = "game_source_mechanics_v1"

_MAX_FILES = 600
_MAX_FILE_BYTES = 768_000
_MAX_EVIDENCE = 8

_SKIP_DIRS = {
    ".git", ".godot", ".import", "library", "temp", "obj", "build", "builds",
    "logs", "node_modules", "__pycache__", ".venv", "venv", "packages",
    "plugins", "addons", "third_party", "thirdparty", "vendor", "dist",
}

LABELS_AR: Dict[str, str] = {
    "player_movement": "حركة اللاعب",
    "player_jump": "القفز",
    "score_system": "نظام النقاط",
    "lives_system": "نظام الأرواح",
    "health_system": "نظام الصحة",
    "timer_system": "المؤقت/الوقت",
    "collision": "التصادم",
    "win_condition": "شرط الفوز",
    "lose_condition": "شرط الخسارة",
    "collect_items": "جمع العناصر",
    "enemy_interaction": "تفاعل العدو",
    "menu_ui": "القائمة/الواجهة",
    "restart_flow": "إعادة التشغيل",
    "sound": "الصوت",
}

S, W = "strong", "weak"
_Rule = Tuple[str, str, str]  # (regex, note, strength)

# ---------------------------------------------------------------- GDScript
_GDSCRIPT: Dict[str, Sequence[_Rule]] = {
    "player_movement": (
        (r"Input\.get_(axis|vector)\s*\(", "Input.get_axis/get_vector", S),
        (r"Input\.is_action_(pressed|just_pressed)\s*\(\s*[\"']ui_(left|right|up|down)[\"']", "ui_left/right action", S),
        (r"Input\.is_action_(pressed|just_pressed)\s*\(\s*[\"']move_\w+[\"']", "move_* action", S),
        (r"\bmove_and_slide\s*\(", "move_and_slide()", W),
        (r"\bvelocity\.x\s*=", "velocity.x assigned", W),
    ),
    "player_jump": (
        (r"Input\.is_action_(just_)?pressed\s*\(\s*[\"'](jump|ui_accept|ui_up)[\"']", "jump action input", S),
        (r"\bvelocity\.y\s*=\s*-?\s*\w*jump\w*", "velocity.y = jump velocity", S),
        (r"\bvelocity\.y\s*=\s*-\s*\d", "upward impulse on velocity.y", S),
        (r"\bis_on_floor\s*\(", "is_on_floor() check", W),
        (r"\bgravity\b", "gravity referenced", W),
    ),
    "score_system": (
        (r"\bscore\s*[+\-]=", "score incremented", S),
        (r"\bpoints?\s*[+\-]=", "points incremented", S),
        (r"\.text\s*=.*score", "score shown in label", W),
    ),
    "lives_system": ((r"\blives\s*[+\-]=", "lives changed", S), (r"\blives\s*(<=|==|<)\s*0", "lives checked", S)),
    "health_system": ((r"\b(health|hp)\s*[+\-]=", "health changed", S), (r"\b(health|hp)\s*(<=|<)\s*0", "health checked", S)),
    "timer_system": ((r"\bTimer\b", "Timer node", S), (r"\b(time_left|time_remaining|countdown)\b", "countdown variable", S), (r"\+=\s*delta\b", "delta accumulated", W)),
    "collision": ((r"body_entered|area_entered", "collision signal", S), (r"get_slide_collision", "slide collision", S), (r"move_and_collide\s*\(", "move_and_collide", S)),
    "win_condition": ((r"\b(you_?win|win|victory|level_complete)\w*\s*\(", "win function", S), (r"[\"'](you win|victory|level complete)", "win text", S)),
    "lose_condition": ((r"\b(game_?over|lose|die|death)\w*\s*\(", "game over function", S), (r"[\"']game ?over", "game over text", S)),
    "collect_items": ((r"\b(coin|gem|collectible|pickup)s?\b.*queue_free|queue_free.*\b(coin|gem|pickup)", "item collected", S), (r"\b(coins?|gems?)\s*[+\-]=", "collectible counter", S)),
    "enemy_interaction": ((r"\benemy\b.*(body_entered|damage|hit|die)", "enemy interaction", S), (r"is_in_group\s*\(\s*[\"']enem", "enemy group", S)),
    "menu_ui": ((r"change_scene(_to_file|_to_packed)?\s*\(", "scene change", W), (r"\b(start|play)_?(button|pressed)", "start button", S)),
    "restart_flow": ((r"reload_current_scene\s*\(", "reload scene", S),),
    "sound": ((r"AudioStreamPlayer|\.play\s*\(\s*\)", "audio playback", W),),
}

# ---------------------------------------------------------------- Unity C#
_CSHARP: Dict[str, Sequence[_Rule]] = {
    "player_movement": (
        (r"Input\.GetAxis(Raw)?\s*\(\s*\"(Horizontal|Vertical)\"", "Input.GetAxis Horizontal/Vertical", S),
        (r"Input\.GetKey(Down)?\s*\(\s*KeyCode\.(LeftArrow|RightArrow|UpArrow|DownArrow|A|D|W|S)\b", "movement key", S),
        (r"\.ReadValue<Vector2>\s*\(", "Input System move vector", S),
        (r"\b(rb|rigidbody\w*|body)\.(velocity|linearVelocity)\s*=", "rigidbody velocity set", W),
        (r"transform\.(Translate|position)\s*[+=(]", "transform moved", W),
        (r"\.Move\s*\(", "CharacterController.Move", W),
    ),
    "player_jump": (
        (r"Input\.GetButton(Down)?\s*\(\s*\"Jump\"", "Jump button", S),
        (r"Input\.GetKey(Down)?\s*\(\s*KeyCode\.Space", "Space key", S),
        (r"AddForce\s*\([^)]*(up|jump)", "upward force", S),
        (r"\bjump\w*\s*\(", "jump method", W),
        (r"\bisGrounded\b|\bgrounded\b", "ground check", W),
    ),
    "score_system": ((r"\bscore\s*(\+\+|\+=|-=)", "score changed", S), (r"\bpoints?\s*(\+\+|\+=)", "points changed", S), (r"\.text\s*=.*[Ss]core", "score UI", W)),
    "lives_system": ((r"\blives\s*(--|-=|\+=|\+\+)", "lives changed", S), (r"\blives\s*(<=|==|<)\s*0", "lives checked", S)),
    "health_system": ((r"\b(health|hp|currentHealth)\s*(--|-=|\+=)", "health changed", S), (r"\b(health|hp|currentHealth)\s*(<=|<)\s*0", "health checked", S)),
    "timer_system": ((r"Time\.deltaTime", "deltaTime accumulated", W), (r"\b(timer|timeLeft|timeRemaining|countdown)\s*(-=|\+=)", "timer variable", S)),
    "collision": ((r"OnCollision(Enter|Stay|Exit)(2D)?\s*\(", "OnCollision", S), (r"OnTrigger(Enter|Stay|Exit)(2D)?\s*\(", "OnTrigger", S)),
    "win_condition": ((r"\b(Win|YouWin|Victory|LevelComplete)\w*\s*\(", "win method", S), (r"\"(you win|victory|level complete)", "win text", S)),
    "lose_condition": ((r"\b(GameOver|Lose|Die|PlayerDeath)\w*\s*\(", "game over method", S), (r"\"game ?over", "game over text", S)),
    "collect_items": ((r"CompareTag\s*\(\s*\"(Coin|Collectible|Pickup|Gem|Item)\"", "collectible tag", S), (r"\b(coins?|gems?)\s*(\+\+|\+=)", "collectible counter", S)),
    "enemy_interaction": ((r"CompareTag\s*\(\s*\"Enemy\"", "enemy tag", S), (r"TakeDamage\s*\(", "damage call", S)),
    "menu_ui": ((r"SceneManager\.LoadScene\s*\(", "scene load", W), (r"\b(StartGame|PlayGame|OnPlay)\w*\s*\(", "start button handler", S)),
    "restart_flow": ((r"LoadScene\s*\(\s*SceneManager\.GetActiveScene", "reload scene", S), (r"\bRestart\w*\s*\(", "restart method", S)),
    "sound": ((r"AudioSource|PlayOneShot\s*\(", "audio", W),),
}

# ---------------------------------------------------------------- Python / pygame
_PYTHON: Dict[str, Sequence[_Rule]] = {
    "player_movement": (
        (r"K_(LEFT|RIGHT|UP|DOWN|a|d|w|s)\b", "arrow/WASD key", S),
        (r"\.(rect\.)?x\s*[+\-]=", "x position changed", W),
        (r"\b(vel|velocity|speed|dx)\w*\s*[+\-]?=", "velocity variable", W),
    ),
    "player_jump": (
        (r"K_SPACE\b", "space key", S),
        (r"\b(vel_?y|y_vel|dy|velocity_y)\s*=\s*-", "upward impulse", S),
        (r"\bjump\w*\s*[=(]", "jump state/method", W),
        (r"\bgravity\b", "gravity", W),
    ),
    "score_system": ((r"\bscore\s*[+\-]=", "score changed", S), (r"render\([^)]*[Ss]core", "score rendered", W)),
    "lives_system": ((r"\blives\s*[+\-]=", "lives changed", S), (r"\blives\s*(<=|==|<)\s*0", "lives checked", S)),
    "health_system": ((r"\b(health|hp)\s*[+\-]=", "health changed", S), (r"\b(health|hp)\s*(<=|<)\s*0", "health checked", S)),
    "timer_system": ((r"pygame\.time\.get_ticks\s*\(", "get_ticks timer", S), (r"\b(timer|time_left|countdown)\s*[+\-]=", "timer variable", S)),
    "collision": ((r"colliderect\s*\(|spritecollide\w*\s*\(|collide_rect", "collision check", S),),
    "win_condition": ((r"[\"'](you win|victory|level complete)", "win text", S), (r"\b(win|victory)\w*\s*=\s*True", "win flag", S)),
    "lose_condition": ((r"[\"']game ?over", "game over text", S), (r"\bgame_?over\s*=\s*True", "game over flag", S)),
    "collect_items": ((r"\b(coins?|gems?|items?_collected)\s*[+\-]=", "collectible counter", S),),
    "enemy_interaction": ((r"\benem(y|ies)\b.*collide|collide.*\benem(y|ies)", "enemy collision", S),),
    "menu_ui": ((r"\b(main_?menu|start_?screen|menu_loop)\s*\(", "menu function", S),),
    "restart_flow": ((r"\b(restart|reset_game|new_game)\s*\(", "restart", S),),
    "sound": ((r"mixer\.(Sound|music)", "pygame mixer", W),),
}

# ---------------------------------------------------------------- JS / TS
_JS: Dict[str, Sequence[_Rule]] = {
    "player_movement": (
        (r"(ArrowLeft|ArrowRight|ArrowUp|ArrowDown|cursors\.(left|right))", "arrow key input", S),
        (r"setVelocityX\s*\(", "setVelocityX", W),
        (r"\.x\s*[+\-]=", "x changed", W),
    ),
    "player_jump": (
        (r"(\"Space\"|' '|\" \"|SPACE|cursors\.up)", "jump key", S),
        (r"setVelocityY\s*\(\s*-", "upward velocity", S),
        (r"\b(vy|velY|velocityY)\s*=\s*-", "upward impulse", S),
        (r"\bgravity\b", "gravity", W),
    ),
    "score_system": ((r"\bscore\s*(\+\+|\+=|-=)", "score changed", S),),
    "lives_system": ((r"\blives\s*(--|-=|\+=)", "lives changed", S),),
    "health_system": ((r"\b(health|hp)\s*(--|-=|\+=)", "health changed", S),),
    "timer_system": ((r"setInterval\s*\(|time\.addEvent\s*\(", "timer", S),),
    "collision": ((r"physics\.add\.(overlap|collider)\s*\(|intersects?\s*\(", "collision", S),),
    "win_condition": ((r"[\"'`](you win|victory|level complete)", "win text", S),),
    "lose_condition": ((r"[\"'`]game ?over", "game over text", S),),
    "collect_items": ((r"\b(coins?|stars?|gems?)\s*(\+\+|\+=)|collect\w*\s*\(", "collect", S),),
    "enemy_interaction": ((r"\benem(y|ies)\b", "enemy referenced", W), (r"hit\w*Enemy|enemy\w*Hit", "enemy hit", S)),
    "menu_ui": ((r"scene\.start\s*\(", "scene start", W),),
    "restart_flow": ((r"scene\.restart\s*\(|location\.reload\s*\(", "restart", S),),
    "sound": ((r"sound\.(play|add)|new Audio\s*\(", "audio", W),),
}

_LANG_BY_EXT: Dict[str, str] = {
    ".gd": "gdscript", ".cs": "csharp", ".py": "python",
    ".js": "javascript", ".ts": "javascript", ".gml": "gml",
}
_RULES = {"gdscript": _GDSCRIPT, "csharp": _CSHARP, "python": _PYTHON, "javascript": _JS}

_COMMENT_PREFIX = {"gdscript": ("#",), "python": ("#",), "csharp": ("//",), "javascript": ("//",)}

# GML notes (from the existing analyzer) that are too weak to prove a mechanic alone.
GML_WEAK_NOTES = {
    "gravity set", "custom gravity variable", "ground check (place_meeting)",
    "x position updated", "speed variable updated", "score drawn on screen",
    "highscore referenced",
}


def _compile(rules: Dict[str, Sequence[_Rule]]) -> Dict[str, List[Tuple[Pattern[str], str, str]]]:
    return {k: [(re.compile(p, re.I), n, s) for p, n, s in v] for k, v in rules.items()}


_COMPILED = {lang: _compile(r) for lang, r in _RULES.items()}


def _iter_source_files(root: Path) -> Iterable[Path]:
    try:
        entries = sorted(root.rglob("*"), key=lambda p: str(p).lower())
    except OSError:
        return []
    out: List[Path] = []
    for p in entries:
        if not p.is_file() or p.suffix.lower() not in _LANG_BY_EXT:
            continue
        rel_parts = {part.lower() for part in p.relative_to(root).parts[:-1]}
        if rel_parts & _SKIP_DIRS:
            continue
        out.append(p)
        if len(out) >= _MAX_FILES:
            break
    return out


def _read_lines(path: Path) -> List[str]:
    try:
        if path.stat().st_size > _MAX_FILE_BYTES:
            return []
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def is_mechanic_proven(evidence: List[Dict[str, Any]]) -> bool:
    """Strong signal, or >=2 distinct weak signals."""
    if any(e.get("strength") == S for e in evidence):
        return True
    return len({e.get("note") for e in evidence if e.get("strength") == W}) >= 2


def _empty_mechanics() -> Dict[str, Dict[str, Any]]:
    return {k: {"detected": False, "label_ar": v, "evidence": []} for k, v in LABELS_AR.items()}


def _merge_gml(mechanics: Dict[str, Dict[str, Any]], root: Optional[Path], gml_files: List[Path]) -> int:
    try:
        from app.runtime_engines.gamemaker.gml_mechanics import analyze_gml_mechanics
    except Exception:
        return 0
    try:
        gml = analyze_gml_mechanics(root, gml_files=gml_files or None)
    except Exception:
        return 0
    for mech_id, row in (gml.get("mechanics") or {}).items():
        bucket = mechanics.setdefault(
            mech_id, {"detected": False, "label_ar": row.get("label_ar") or mech_id, "evidence": []}
        )
        for ev in row.get("evidence") or []:
            if len(bucket["evidence"]) >= _MAX_EVIDENCE:
                break
            ev = dict(ev)
            ev["strength"] = W if ev.get("note") in GML_WEAK_NOTES else S
            ev["language"] = "gml"
            bucket["evidence"].append(ev)
    return int(gml.get("gml_files_scanned") or 0)


def analyze_source_mechanics(
    root: Optional[Path] = None,
    *,
    files: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    """Scan student source code (any supported engine) for gameplay mechanics."""
    candidates: List[Path] = []
    if files:
        candidates.extend(Path(f) for f in files if Path(f).suffix.lower() in _LANG_BY_EXT)
    if root and Path(root).is_dir():
        candidates.extend(_iter_source_files(Path(root)))
    uniq = sorted({p.resolve() for p in candidates if p.is_file()}, key=lambda p: str(p).lower())[:_MAX_FILES]

    mechanics = _empty_mechanics()
    languages: Dict[str, int] = {}
    gml_files = [p for p in uniq if p.suffix.lower() == ".gml"]
    yyp_root: Optional[Path] = None
    if root and Path(root).is_dir():
        yyps = sorted(Path(root).rglob("*.yyp"))
        yyp_root = yyps[0].parent if yyps else None
    scanned = 0
    if gml_files or yyp_root:
        scanned += _merge_gml(mechanics, yyp_root, gml_files)
        languages["gml"] = len(gml_files)

    for fp in uniq:
        lang = _LANG_BY_EXT.get(fp.suffix.lower())
        if lang == "gml" or lang not in _COMPILED:
            continue
        lines = _read_lines(fp)
        if not lines:
            continue
        scanned += 1
        languages[lang] = languages.get(lang, 0) + 1
        prefixes = _COMMENT_PREFIX.get(lang, ())
        for lineno, raw in enumerate(lines, start=1):
            line = raw.strip()
            if not line or line.startswith(prefixes):
                continue
            for mech_id, rules in _COMPILED[lang].items():
                bucket = mechanics[mech_id]
                if len(bucket["evidence"]) >= _MAX_EVIDENCE:
                    continue
                for creg, note, strength in rules:
                    if creg.search(line):
                        bucket["evidence"].append({
                            "file": str(fp), "line": lineno, "snippet": line[:160],
                            "note": note, "strength": strength, "language": lang,
                        })
                        break

    for row in mechanics.values():
        row["detected"] = is_mechanic_proven(row["evidence"])
    detected = sorted(k for k, v in mechanics.items() if v["detected"])
    return {
        "version": SOURCE_MECHANICS_VERSION,
        "mechanics": mechanics,
        "detected_ids": detected,
        "languages": languages,
        "files_scanned": scanned,
        "deterministic": True,
        "findings_ar": [
            f"تم رصد {mechanics[m]['label_ar']} في الكود ({len(mechanics[m]['evidence'])} دليل)"
            for m in detected
        ],
    }
