"""Feature-First Evidence Architecture for Godot projects (Pearson BTEC).

Mandate (2026-07-07): the grader MUST distinguish two independent states per
feature and never conflate them:

  1. IMPLEMENTATION (feature existence) — proven ONLY by static analysis of the
     complete project (*.gd, *.tscn, *.tres, project.godot): code lines, scene
     graph, input map, resource references.
  2. RUNTIME — proven ONLY by an honest run (launch, window, gameplay entered,
     input accepted, alive, no crash, minimum duration).

Hard rules implemented here:
  - Static analysis NEVER claims runtime success ("implementation detected",
    never "works").
  - Runtime NEVER determines feature existence.
  - A runtime/capture failure NEVER erases static implementation evidence
    (it only marks Runtime: FAILED with an environment reason).
  - Every feature carries: evidence lines, source files, scenes, input actions,
    confidence, and the two independent states.

Deterministic: same project bytes -> same matrix. No AI calls.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

FEATURE_EVIDENCE_VERSION = "godot_feature_evidence_v1"

_MAX_FILE_BYTES = 2_000_000
_MAX_EVIDENCE_PER_FEATURE = 8

# Capture/environment failure codes: runtime FAILED (environment), never the
# student's fault, and never proof that features are absent.
_ENV_FAILURE_CODES = frozenset(
    {"GAME_WINDOW_CAPTURE_FAILED", "WINDOW_NOT_FOUND", "BOOT_TIMEOUT"}
)


@dataclass
class _FeatureSpec:
    feature_id: str
    label_ar: str
    label_en: str
    gd_patterns: List[str] = field(default_factory=list)
    tscn_patterns: List[str] = field(default_factory=list)
    input_actions: List[str] = field(default_factory=list)
    runtime_gv_keys: List[str] = field(default_factory=list)


_SPECS: List[_FeatureSpec] = [
    _FeatureSpec(
        "player_movement", "حركة اللاعب", "Player movement",
        gd_patterns=[r"move_and_slide", r"move_and_collide", r"velocity\.x\s*[-+*]?="],
        input_actions=["ui_left", "ui_right", "move_left", "move_right"],
        runtime_gv_keys=["player_movement_verified"],
    ),
    _FeatureSpec(
        "jump", "القفز", "Jump",
        gd_patterns=[r"velocity\.y\s*[-+]?=", r"\bjump\b", r"JUMP_FORCE|JUMP_VELOCITY"],
        input_actions=["ui_accept", "ui_up", "jump"],
        runtime_gv_keys=["jump_detected"],
    ),
    _FeatureSpec(
        "gravity", "الجاذبية", "Gravity",
        gd_patterns=[r"\bgravity\b", r"GRAVITY"],
    ),
    _FeatureSpec(
        "lives_health", "الأرواح/الصحة", "Lives / Health",
        gd_patterns=[r"\blives\b", r"\bhealth\b", r"\bhp\b", r"hearts"],
    ),
    _FeatureSpec(
        "timer", "المؤقت", "Timer",
        gd_patterns=[r"\bTimer\b", r"wait_time", r"\btimeout\b", r"time_left", r"الوقت"],
        tscn_patterns=[r'type="Timer"'],
    ),
    _FeatureSpec(
        "score", "النقاط", "Score",
        gd_patterns=[r"\bscore\b", r"\bpoints\b", r"النقاط"],
        runtime_gv_keys=["score_change_detected"],
    ),
    _FeatureSpec(
        "collectibles", "جمع العناصر", "Collectibles",
        gd_patterns=[r"collect", r"\bcoin\b", r"\bfruit\b", r"pickup", r"\bitem\b"],
    ),
    _FeatureSpec(
        "enemy_ai", "العدو/الذكاء", "Enemy AI",
        gd_patterns=[r"\benemy\b", r"\bchase\b", r"\bpatrol\b", r"\bEnemy\b"],
    ),
    _FeatureSpec(
        "collision", "التصادم", "Collision",
        gd_patterns=[r"body_entered", r"area_entered", r"_on_.*_body_entered"],
        tscn_patterns=[r'type="CollisionShape2D"', r'type="CollisionShape3D"', r'type="Area2D"'],
    ),
    _FeatureSpec(
        "animation", "الحركة الرسومية", "Animation",
        gd_patterns=[r"AnimationPlayer", r"AnimatedSprite", r"\.play\("],
        tscn_patterns=[r'type="AnimationPlayer"', r'type="AnimatedSprite2D"'],
    ),
    _FeatureSpec(
        "ui_hud", "الواجهة/HUD", "UI / HUD",
        gd_patterns=[r"\bLabel\b", r"CanvasLayer", r"\.text\s*="],
        tscn_patterns=[r'type="Label"', r'type="CanvasLayer"', r'type="Control"'],
    ),
    _FeatureSpec(
        "main_menu", "القائمة الرئيسية", "Main menu",
        gd_patterns=[r"main_menu", r"MainMenu", r"start_game", r"change_scene"],
        tscn_patterns=[r"[Mm]enu"],
    ),
    _FeatureSpec(
        "pause_menu", "قائمة الإيقاف", "Pause menu",
        gd_patterns=[r"\bpause\b", r"paused\s*="],
    ),
    _FeatureSpec(
        "win_screen", "شاشة الفوز", "Win screen",
        gd_patterns=[r"\bwin\b", r"victory", r"you_won|YouWin"],
        tscn_patterns=[r"[Ww]in"],
    ),
    _FeatureSpec(
        "lose_screen", "شاشة الخسارة", "Lose screen",
        gd_patterns=[r"game_over", r"\blose\b", r"\bdeath\b|\bdie\b"],
        tscn_patterns=[r"[Gg]ame[_ ]?[Oo]ver|[Ll]ose"],
    ),
    _FeatureSpec(
        "multiple_levels", "تعدد المستويات", "Multiple levels",
        gd_patterns=[r"level_\d|Level\d|next_level"],
        tscn_patterns=[r"[Ll]evel"],
    ),
    _FeatureSpec(
        "audio", "الصوت", "Audio",
        gd_patterns=[r"AudioStreamPlayer", r"\.play\(\)\s*#?\s*(sound|audio)?"],
        tscn_patterns=[r'type="AudioStreamPlayer'],
    ),
    _FeatureSpec(
        "save_system", "نظام الحفظ", "Save system",
        gd_patterns=[r"FileAccess", r"ConfigFile", r"user://", r"\bsave\b"],
    ),
]


def _iter_project_files(root: Path) -> List[Path]:
    exts = {".gd", ".tscn", ".tres", ".res", ".godot", ".cfg"}
    files: List[Path] = []
    try:
        for p in sorted(root.rglob("*")):
            if p.is_file() and (p.suffix.lower() in exts or p.name == "project.godot"):
                files.append(p)
    except OSError:
        pass
    return files


def _read_text(path: Path) -> str:
    try:
        if path.stat().st_size > _MAX_FILE_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _input_map_actions(project_godot_text: str) -> List[str]:
    actions: List[str] = []
    in_input = False
    for line in project_godot_text.splitlines():
        s = line.strip()
        if s.startswith("[input]"):
            in_input = True
            continue
        if in_input and s.startswith("[") and s.endswith("]"):
            break
        if in_input:
            m = re.match(r"^([A-Za-z0-9_]+)\s*=", s)
            if m:
                actions.append(m.group(1))
    return actions


def scan_godot_project(project_root: str | Path) -> Dict[str, Any]:
    """RULE 1: static analysis proves feature EXISTENCE only (never runtime)."""
    root = Path(project_root)
    files = _iter_project_files(root)
    texts: Dict[Path, str] = {p: _read_text(p) for p in files}
    gd_files = [p for p in files if p.suffix == ".gd"]
    tscn_files = [p for p in files if p.suffix == ".tscn"]
    project_files = [p for p in files if p.name == "project.godot"]
    input_actions = []
    for p in project_files:
        input_actions.extend(_input_map_actions(texts.get(p, "")))

    features: List[Dict[str, Any]] = []
    for spec in _SPECS:
        evidence: List[Dict[str, Any]] = []
        scenes: List[str] = []
        for p in gd_files:
            text = texts.get(p, "")
            if not text:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if len(evidence) >= _MAX_EVIDENCE_PER_FEATURE:
                    break
                for pat in spec.gd_patterns:
                    if re.search(pat, line):
                        evidence.append(
                            {
                                "file": str(p.relative_to(root)) if root in p.parents or p == root else str(p),
                                "line": i,
                                "snippet": line.strip()[:160],
                                "kind": "gd",
                            }
                        )
                        break
        for p in tscn_files:
            text = texts.get(p, "")
            if not text:
                continue
            for pat in spec.tscn_patterns:
                if re.search(pat, text) or re.search(pat, p.name):
                    rel = str(p.relative_to(root)) if root in p.parents else str(p)
                    if rel not in scenes:
                        scenes.append(rel)
                    if len(evidence) < _MAX_EVIDENCE_PER_FEATURE:
                        evidence.append(
                            {"file": rel, "line": 0, "snippet": f"scene matches /{pat}/", "kind": "tscn"}
                        )
                    break
        matched_actions = [a for a in spec.input_actions if a in input_actions]
        exists = bool(evidence)
        evidence_sources: List[str] = []
        if any(e["kind"] == "gd" for e in evidence):
            evidence_sources.append("code")
        if scenes or any(e["kind"] == "tscn" for e in evidence):
            evidence_sources.append("scene")
        if matched_actions:
            evidence_sources.append("input_map")
        gd_hits = sum(1 for e in evidence if e["kind"] == "gd")
        confidence = 0
        if exists:
            confidence = 60
            if gd_hits >= 2:
                confidence = 80
            if gd_hits >= 2 and (scenes or matched_actions):
                confidence = 95
            if gd_hits >= 2 and scenes and matched_actions:
                confidence = 100
        features.append(
            {
                "feature_id": spec.feature_id,
                "label_ar": spec.label_ar,
                "label_en": spec.label_en,
                # IMPLEMENTED (not "PASS"): Pearson reports reserve PASS for criterion
                # achievement; static analysis only proves the implementation exists.
                "implementation": "IMPLEMENTED" if exists else "NOT_FOUND",
                "implementation_confidence": confidence,
                "evidence": evidence,
                "evidence_sources": evidence_sources,
                "scenes": scenes,
                "input_actions": matched_actions,
                # RULE 2: wording must never claim runtime success.
                "statement_ar": (
                    f"تم رصد تنفيذ «{spec.label_ar}» في الكود/المشاهد (تحليل ساكن)."
                    if exists
                    else f"لم يُعثر على تنفيذ «{spec.label_ar}» في ملفات المشروع."
                ),
                "statement_en": (
                    f"{spec.label_en} implementation detected (static analysis)."
                    if exists
                    else f"No {spec.label_en} implementation found in project files."
                ),
                # RULE 3/4: runtime is an independent state, set by merge only.
                "runtime": "NOT_VERIFIED",
                "runtime_reason": "",
                "_runtime_gv_keys": spec.runtime_gv_keys,
            }
        )
    return {
        "version": FEATURE_EVIDENCE_VERSION,
        "engine": "godot",
        "files_scanned": len(files),
        "gd_files": len(gd_files),
        "tscn_files": len(tscn_files),
        "input_map_actions": input_actions,
        "features": features,
    }


def merge_runtime_states(matrix: Dict[str, Any], gameplay_verification: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """RULE 3/4/5: attach the independent runtime state per feature.

    Runtime answers ONLY "did the game run / was this mechanic honestly observed".
    A capture/environment failure marks runtime FAILED (environment) and NEVER
    touches implementation evidence.
    """
    gv = gameplay_verification if isinstance(gameplay_verification, dict) else {}
    out = dict(matrix)
    entered = gv.get("gameplay_entered") is True
    failure_code = str(gv.get("failure_reason_code") or "")
    env_failed = failure_code in _ENV_FAILURE_CODES
    session = {
        "launched": bool(gv) or entered,
        "gameplay_entered": entered,
        "failure_reason_code": failure_code or None,
        "environment_failure": env_failed,
    }
    features = []
    for feat in out.get("features", []):
        f = dict(feat)
        keys = f.pop("_runtime_gv_keys", []) or []
        if entered and any(gv.get(k) is True for k in keys):
            f["runtime"] = "VERIFIED"
            f["runtime_reason"] = "observed during honest gameplay session"
        elif env_failed:
            f["runtime"] = "FAILED_ENVIRONMENT"
            f["runtime_reason"] = (
                "Capture environment failure — does not invalidate static analysis. "
                "Manual review recommended."
            )
        else:
            f["runtime"] = "NOT_VERIFIED"
            f["runtime_reason"] = "runtime execution was not verified in this grading session"
        features.append(f)
    out["features"] = features
    out["runtime_session"] = session
    # RULE 8: mandated closing statement.
    out["mandated_statement_ar"] = (
        "تم التحقق من التنفيذ تحليلياً (ساكن). لم يتأكد التنفيذ التشغيلي في هذه الجلسة. "
        "المطلوب playtest يدوي أو تشغيل ناجح للتحقق من التنفيذ الفعلي فقط — لا لإثبات وجود التنفيذ."
        if not entered
        else "تم التحقق من التنفيذ تحليلياً، ودخل التشغيل إلى gameplay في هذه الجلسة."
    )
    out["mandated_statement_en"] = (
        "The implementation has been verified statically. Runtime execution could not be "
        "confirmed during this session. A manual playtest or successful runtime verification "
        "is required only for validating execution, not for proving implementation."
        if not entered
        else "The implementation has been verified statically and the session entered gameplay."
    )
    return out


def build_feature_evidence(project_root: str | Path, gameplay_verification: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One-call API: static scan + independent runtime merge."""
    return merge_runtime_states(scan_godot_project(project_root), gameplay_verification)
