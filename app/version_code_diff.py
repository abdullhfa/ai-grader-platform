"""
V1 → V2 code-diff evidence for the C.M3 gate ("improve the game").

A student's *claim* of an improvement is never evidence.  This module locates the
two supplied versions on disk, diffs their real source/asset files, and links every
improvement claim found in the student's write-up to a change that exists in the
diff.  A claim with no matching change stays ``unsupported`` and does not count.

Design rules (deterministic, no AI):
  * Versions are found from directory names (v1/v2, initial/final, Arabic cues).
    The *version group* is the marker folder itself when it holds the project, or
    its parent when the marker only names a build folder (e.g. ``Design/V1`` next
    to ``Design/code``).  Both groups must be disjoint, otherwise the versions
    are reported as ``versions_not_separable`` — never guessed.
  * Only substantive changes count: comments, blank lines and whitespace are
    stripped before diffing; asset files are compared by content hash.
  * Claims are read only from sentences that contain an improvement cue.
  * ``ok`` requires ≥1 supported claim and a supported ratio ≥ 0.5, so a write-up
    whose improvement story is mostly absent from the code does not open M3.
"""
from __future__ import annotations

import difflib
import hashlib
import io
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

CODE_DIFF_VERSION = "version_code_diff_v1"


def _nre(pattern: str, flags: int = re.IGNORECASE) -> "re.Pattern[str]":
    """Compile a pattern after the same Arabic normalisation applied to student text."""
    from app.arabic_text_normalize import normalize_arabic_text

    return re.compile(normalize_arabic_text(pattern), flags)

MIN_SUPPORTED_CLAIMS = 1
MIN_SUPPORTED_RATIO = 0.5

_MAX_FILES_PER_VERSION = 4000
_MAX_TEXT_BYTES = 2_000_000
_MAX_ASSET_BYTES = 40_000_000
_MAX_WALK_ENTRIES = 60_000
_MAX_DEPTH = 14
_MAX_CLAIMS = 24

_CODE_EXT = frozenset(
    {".gml", ".gd", ".cs", ".js", ".ts", ".py", ".lua", ".java", ".cpp", ".c", ".h", ".hpp"}
)
# Scene / object metadata that carries behaviour (collision masks, rooms, prefabs).
_META_EXT = frozenset({".yy", ".tscn", ".tres", ".unity", ".prefab", ".scene", ".asset"})
_ASSET_EXT = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".wav", ".mp3", ".ogg", ".ttf", ".otf"})
_SCRATCH_EXT = frozenset({".sb3"})
# Listing files that change with every added resource; not behavioural evidence.
_NEVER_DIFF_NAMES = frozenset({".yyp", ".resource_order"})
_NEVER_DIFF_SUFFIXES = (".yyp", ".resource_order", ".meta", ".import")

_SKIP_DIR_NAMES = frozenset(
    {
        "library", "temp", "tmp", "obj", "bin", "node_modules", ".godot", ".import",
        ".git", ".vs", ".idea", "__pycache__", "__macosx", "embedruntime",
        "monobleedingedge", "packages",
    }
)

_V1_TOKEN = _nre(
    r"(?:^|[\s_\-.])(?:v(?:er(?:sion)?)?[\s_\-]?1|initial|prototype|draft|original|first)(?:$|[\s_\-.])"
    r"|النسخة\s*(?:ال)?[أا]ول[ىي]|[أا]ولي[ةه]|نسخة\s*1",
    re.IGNORECASE,
)
_V2_TOKEN = _nre(
    r"(?:^|[\s_\-.])(?:v(?:er(?:sion)?)?[\s_\-]?2|final|improved|refined|updated|polish(?:ed)?)(?:$|[\s_\-.])"
    r"|النسخة\s*(?:ال)?(?:ثانية|نهائية|محسنة)|النهائية|محسنة|نسخة\s*2",
    re.IGNORECASE,
)
# Explicit numeric markers outrank descriptive words when a name hits both.
_V1_NUM = re.compile(r"(?:^|[\s_\-.])v(?:er(?:sion)?)?[\s_\-]?1(?:$|[\s_\-.])", re.IGNORECASE)
_V2_NUM = re.compile(r"(?:^|[\s_\-.])v(?:er(?:sion)?)?[\s_\-]?2(?:$|[\s_\-.])", re.IGNORECASE)

_PROJECT_MARKER_SUFFIX = (".yyp", ".sb3")
_PROJECT_MARKER_NAMES = frozenset({"project.godot", "projectsettings"})


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def _band_of_component(name: str) -> Optional[int]:
    from app.arabic_text_normalize import normalize_arabic_text

    n = normalize_arabic_text(name)
    if _V1_NUM.search(n) and not _V2_NUM.search(n):
        return 1
    if _V2_NUM.search(n) and not _V1_NUM.search(n):
        return 2
    a, b = bool(_V1_TOKEN.search(n)), bool(_V2_TOKEN.search(n))
    if a and not b:
        return 1
    if b and not a:
        return 2
    return None


def _iter_files(root: Path) -> Iterable[Path]:
    """Bounded walk that prunes heavy/irrelevant directories instead of visiting them."""
    seen = 0
    root = root.resolve()
    base_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).parts) - base_depth
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in _SKIP_DIR_NAMES and depth < _MAX_DEPTH
        ]
        for fn in filenames:
            seen += 1
            if seen > _MAX_WALK_ENTRIES:
                return
            f = Path(dirpath) / fn
            if f.is_symlink():
                continue  # never follow links out of the student's folder
            yield f


def _is_candidate(path: Path) -> bool:
    ext = path.suffix.lower()
    name = path.name.lower()
    if name in _NEVER_DIFF_NAMES or name.endswith(_NEVER_DIFF_SUFFIXES):
        return False
    return ext in _CODE_EXT or ext in _META_EXT or ext in _ASSET_EXT or ext in _SCRATCH_EXT


def _project_root_of(files: List[Path], group_root: Path) -> Path:
    """Nearest project root (holds .yyp / project.godot / ProjectSettings) with most files."""
    candidates: Dict[Path, int] = {}
    for f in files:
        cur = f.parent
        while True:
            try:
                names = {c.name.lower() for c in cur.iterdir()}
            except OSError:
                names = set()
            if any(n.endswith(_PROJECT_MARKER_SUFFIX) for n in names) or (names & _PROJECT_MARKER_NAMES):
                candidates[cur] = candidates.get(cur, 0) + 1
                break
            if cur == group_root or cur.parent == cur:
                break
            cur = cur.parent
    if not candidates:
        return group_root
    # Prefer the deepest project root among the ones holding the most files.
    best = max(candidates.items(), key=lambda kv: (kv[1], len(kv[0].parts)))
    return best[0]


def discover_version_groups(root: Path) -> Dict[str, Any]:
    """Find disjoint V1 / V2 file groups under ``root``.  Never guesses."""
    root = Path(root)
    if not root.is_dir():
        return {"status": "versions_not_found", "v1": None, "v2": None}

    markers: Dict[int, List[Path]] = {1: [], 2: []}
    all_files = [f for f in _iter_files(root) if _is_candidate(f)]
    dirs: set[Path] = set()
    for f in all_files:
        cur = f.parent
        while cur != root and cur.parent != cur:
            dirs.add(cur)
            cur = cur.parent
    # Marker folders may hold only builds (no candidate files) — include every dir.
    for dirpath, dirnames, _ in os.walk(root):
        depth = len(Path(dirpath).parts) - len(root.resolve().parts)
        dirnames[:] = [d for d in dirnames if d.lower() not in _SKIP_DIR_NAMES and depth < _MAX_DEPTH]
        for d in dirnames:
            dirs.add(Path(dirpath) / d)

    for d in sorted(dirs):
        band = _band_of_component(d.name)
        if band:
            markers[band].append(d)

    if not markers[1] or not markers[2]:
        return {"status": "versions_not_found", "v1": None, "v2": None}

    def files_under(group: Path) -> List[Path]:
        return [f for f in all_files if _is_within(f, group)]

    project_ext = _CODE_EXT | _META_EXT | _SCRATCH_EXT

    def holds_project(group: Path) -> bool:
        # A folder that only holds a splash image / icon is a *build* folder.
        return any(f.suffix.lower() in project_ext for f in files_under(group))

    def group_root_for(marker: Path, band: int) -> Optional[Path]:
        if holds_project(marker):
            return marker
        parent = marker.parent
        if parent == root.parent or not _is_within(parent, root) and parent != root:
            return None
        # The parent must not also hold the *other* version's marker.
        other = 2 if band == 1 else 1
        if any(_is_within(m, parent) for m in markers[other]):
            return None
        return parent if holds_project(parent) else None

    g1 = [g for g in (group_root_for(m, 1) for m in markers[1]) if g]
    g2 = [g for g in (group_root_for(m, 2) for m in markers[2]) if g]
    if not g1 or not g2:
        return {"status": "versions_not_separable", "v1": None, "v2": None}

    # Pick the group with most candidate files per band; require disjoint trees.
    r1 = max(set(g1), key=lambda g: len(files_under(g)))
    r2 = max(set(g2), key=lambda g: len(files_under(g)))
    if _is_within(r1, r2) or _is_within(r2, r1):
        return {"status": "versions_not_separable", "v1": None, "v2": None}

    f1, f2 = files_under(r1), files_under(r2)
    return {
        "status": "ok",
        "v1": {"group_root": r1, "project_root": _project_root_of(f1, r1), "files": f1},
        "v2": {"group_root": r2, "project_root": _project_root_of(f2, r2), "files": f2},
    }


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# Normalisation + diff
# --------------------------------------------------------------------------- #
_LINE_COMMENT_HASH = frozenset({".gd", ".py"})


def _strip_comments(text: str, ext: str) -> str:
    if ext in _LINE_COMMENT_HASH:
        return re.sub(r"(?m)#.*$", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)//.*$", "", text)


def _normalise_lines(text: str, ext: str) -> List[str]:
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    if ext in _CODE_EXT:
        text = _strip_comments(text, ext)
    out: List[str] = []
    for raw in text.split("\n"):
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            out.append(line)
    return out


def _sb3_pseudo_lines(path: Path) -> Dict[str, List[str]]:
    """Scratch: flatten each sprite's blocks to comparable lines (opcode + literals)."""
    result: Dict[str, List[str]] = {}
    try:
        with zipfile.ZipFile(path) as z:
            data = json.loads(z.read("project.json").decode("utf-8", "ignore"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return result
    for target in data.get("targets") or []:
        name = str(target.get("name") or "target")
        lines: List[str] = []
        for _bid, blk in sorted((target.get("blocks") or {}).items()):
            if not isinstance(blk, dict):
                continue
            parts = [str(blk.get("opcode") or "")]
            for k, v in sorted((blk.get("fields") or {}).items()):
                parts.append(f"{k}={v[0] if isinstance(v, list) and v else v}")
            for k, v in sorted((blk.get("inputs") or {}).items()):
                lit = v[1] if isinstance(v, list) and len(v) > 1 else v
                if isinstance(lit, list) and len(lit) > 1 and not isinstance(lit[1], (dict, list)):
                    parts.append(f"{k}={lit[1]}")
            lines.append(" ".join(parts))
        result[f"sb3:{name}"] = lines
    return result


def _read_text(path: Path) -> Optional[str]:
    try:
        if path.stat().st_size > _MAX_TEXT_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def _sha256(path: Path) -> Optional[str]:
    try:
        if path.stat().st_size > _MAX_ASSET_BYTES:
            return f"size:{path.stat().st_size}"
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _snapshot(version: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """rel-path (from project root) -> {'kind','lines'|'hash'}"""
    base: Path = version["project_root"]
    snap: Dict[str, Dict[str, Any]] = {}
    for f in version["files"][:_MAX_FILES_PER_VERSION]:
        try:
            rel = f.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            rel = f.name
        ext = f.suffix.lower()
        if ext in _SCRATCH_EXT:
            for key, lines in _sb3_pseudo_lines(f).items():
                snap[f"{rel}::{key}"] = {"kind": "code", "lines": lines}
            continue
        if ext in _ASSET_EXT:
            h = _sha256(f)
            if h:
                snap[rel] = {"kind": "asset", "hash": h}
            continue
        text = _read_text(f)
        if text is None:
            continue
        kind = "code" if ext in _CODE_EXT else "meta"
        snap[rel] = {"kind": kind, "lines": _normalise_lines(text, ext)}
    return snap


def compute_code_diff(v1: Dict[str, Any], v2: Dict[str, Any]) -> Dict[str, Any]:
    s1, s2 = _snapshot(v1), _snapshot(v2)
    changes: List[Dict[str, Any]] = []
    for rel in sorted(set(s1) | set(s2)):
        a, b = s1.get(rel), s2.get(rel)
        if a is None:
            row = {"path": rel, "change": "added", "kind": b["kind"]}
            row["added_lines"] = list(b.get("lines") or [])
            row["removed_lines"] = []
            changes.append(row)
            continue
        if b is None:
            row = {"path": rel, "change": "removed", "kind": a["kind"]}
            row["added_lines"], row["removed_lines"] = [], list(a.get("lines") or [])
            changes.append(row)
            continue
        if a["kind"] == "asset":
            if a.get("hash") != b.get("hash"):
                changes.append(
                    {"path": rel, "change": "modified", "kind": "asset", "added_lines": [], "removed_lines": []}
                )
            continue
        la, lb = a["lines"], b["lines"]
        if la == lb:
            continue
        added: List[str] = []
        removed: List[str] = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=la, b=lb, autojunk=False).get_opcodes():
            if tag in ("replace", "insert"):
                added.extend(lb[j1:j2])
            if tag in ("replace", "delete"):
                removed.extend(la[i1:i2])
        if added or removed:
            changes.append(
                {"path": rel, "change": "modified", "kind": a["kind"], "added_lines": added, "removed_lines": removed}
            )
    substantive = [c for c in changes if c["kind"] in ("code", "meta", "asset")]
    return {
        "files_v1": len(s1),
        "files_v2": len(s2),
        "changes": changes,
        "substantive_change_count": len(substantive),
        "code_change_count": len([c for c in changes if c["kind"] == "code"]),
    }


# --------------------------------------------------------------------------- #
# Claims → evidence
# --------------------------------------------------------------------------- #
_IMPROVE_CUE = _nre(
    r"تحسين|حسّن|حسنت|عدّلت|عدلت|أضفت|اضفت|زدت|زيادة|إعادة ضبط|اعادة ضبط|ضبطت|"
    r"ضغطت|أدخلت|ادخلت|أصلحت|اصلحت|وسّعت|وسعت|استبدلت|استبدال|"
    r"improv|\badded\b|\bfix(?:ed)?\b|adjust|tweak|optimi[sz]|refactor|enhanc",
    re.IGNORECASE,
)
# Promises about a *future* update are not claims of a finished improvement.
_FUTURE_MARK = _nre(r"سا[أ]?عمل|سأ|سوف|سنقوم|القادم|المقبل|\bwill\b|\bfuture\b|next update", re.IGNORECASE)
_CLAIM_WINDOW_BEFORE = 60
_CLAIM_WINDOW_AFTER = 170


class _Rule:
    def __init__(self, cid: str, label: str, claim: str, evidence: str, kinds: Tuple[str, ...] = ("code",),
                 path_evidence: str = "", accept_asset_change: bool = False) -> None:
        self.id = cid
        self.label = label
        self.claim = _nre(claim)
        self.evidence = re.compile(evidence, re.IGNORECASE) if evidence else None
        self.kinds = kinds
        self.path_evidence = re.compile(path_evidence, re.IGNORECASE) if path_evidence else None
        self.accept_asset_change = accept_asset_change


_RULES: Tuple[_Rule, ...] = (
    _Rule("movement_speed", "سرعة/استجابة حركة اللاعب",
          r"سرعة|حساسي|استجاب|speed|sensitiv|responsive",
          r"\b(?:spd|speed|velocity|move_?speed|move_?spd|acceleration|friction|hspeed|vspeed)\w*\s*[-+*/]?=|"
          r"\bSPEED\b|move_and_slide|Input\.GetAxis"),
    _Rule("collision", "التصادم/أقنعة التصادم",
          r"تصادم|قناع|أقنعة|اقنعة|collision|mask|bounding|hitbox",
          r"place_meeting|instance_place|collision_\w+|OnCollision|OnTrigger|CollisionShape|move_and_collide|"
          r"bbox_(?:left|right|top|bottom)|collisionKind|sepmasks",
          kinds=("code", "meta")),
    _Rule("invincibility", "الحماية المؤقتة/الوميض",
          r"حماية مؤقت|الحماية المؤقت|وميض|invincib|i-?frame|grace period|immunity",
          r"invincib|iframe|i_frames|immun|grace|shield|blink|safe_time"),
    _Rule("lives_health", "الأرواح/الصحة",
          r"أرواح|ارواح|صحة|قلوب|lives|health|hearts",
          r"global\.lives|\blives\b|health|\bhp\b|heart|spr_life"),
    _Rule("score_sync", "مزامنة النقاط/الجبن",
          r"عداد|نقاط|مزامنة|score|counter|sync",
          r"global\.score|score\s*[-+]?=|collected|instance_destroy|queue_free|Destroy\("),
    _Rule("audio", "الصوت/الموسيقى",
          r"صوت|موسيق|audio|music|sound",
          r"audio_|\bsound|\bmusic|AudioSource|AudioStream|\.play\(|volume",
          accept_asset_change=True),
    _Rule("performance", "الأداء/الذاكرة",
          r"أداء|اداء|ذاكرة|lag|بطء|performance|memory|delta ?time",
          r"delta_time|deltaTime|_delta\b|gc_collect|surface_free|object_?pool|preload"),
    _Rule("state_transition", "الانتقال بين الحالات/الغرف",
          r"انتقال|room|transition|scene",
          r"room_goto|room_restart|SceneManager|LoadScene|change_scene|gc_collect",
          kinds=("code",)),
    _Rule("tutorial", "غرفة/شاشة تعليمية",
          r"تعليمي|إرشاد|ارشاد|تعليمات|tutorial|how to play|instructions",
          r"how ?to ?play|tutorial|instruction|help_?screen",
          kinds=("code",), path_evidence=r"tutorial|how_?to|instruction|help|guide"),
    _Rule("new_level", "مستوى/صعوبة جديدة",
          r"مستوى جديد|مستويات جديد|صعوب|difficulty|new level|extra level",
          r"diff_\w+\s*=|difficulty|room_goto|\bhard\b|\bwave\b",
          kinds=("code",), path_evidence=r"level|stage"),
    _Rule("enemy_ai", "سلوك الأعداء",
          r"أعداء|اعداء|enemy|chase|مطاردة",
          r"chase|enemy|navigation|\bfollow|dir_[xy]|move_spd|cat_"),
    _Rule("ui_visual", "الواجهة/المظهر",
          r"واجهة|مظهر|ألوان|الوان|خطوط|قلوب|\bui\b|hud|colou?r|font|visual",
          r"draw_set_colou?r|make_colou?r|draw_sprite\w*|draw_text\w*|\bfont\w*|modulate|\bhud\b",
          kinds=("code",), accept_asset_change=True),
    _Rule("map_layout", "تصميم الخريطة/الممرات",
          r"ممر|متاهة|خريطة|maze|layout|corridor",
          r"\bgrid\b|tilemap|maze|corridor",
          kinds=("code",)),
)


def extract_improvement_claims(text: str) -> List[Dict[str, Any]]:
    """One claim per category, from a short window around an improvement cue.

    Windows (not whole paragraphs) keep generic prose — design options, target
    audience, etc. — from being mistaken for an improvement claim.
    """
    if not text:
        return []
    from app.arabic_text_normalize import normalize_arabic_text

    norm = re.sub(r"\s+", " ", normalize_arabic_text(text))
    claims: Dict[str, Dict[str, Any]] = {}
    for cue in _IMPROVE_CUE.finditer(norm):
        start = max(0, cue.start() - _CLAIM_WINDOW_BEFORE)
        window = norm[start: cue.end() + _CLAIM_WINDOW_AFTER]
        if _FUTURE_MARK.search(norm[start: cue.end() + 25]):
            continue
        for rule in _RULES:
            if rule.id not in claims and rule.claim.search(window):
                claims[rule.id] = {"id": rule.id, "label": rule.label, "sentence": window.strip()[:200]}
        if len(claims) >= _MAX_CLAIMS:
            break
    return list(claims.values())


def _link_claim(rule: _Rule, changes: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Evidence = a real change in V2 (added/changed lines, new files, changed assets)."""
    evidence: List[Dict[str, str]] = []
    for ch in changes:
        kind = ch["kind"]
        path = ch["path"]
        if kind == "asset":
            if rule.accept_asset_change and _asset_relevant(rule, path):
                evidence.append({"path": path, "how": f"asset_{ch['change']}"})
        elif kind in rule.kinds and rule.evidence and not (kind == "meta" and ch["change"] != "modified"):
            for line in ch.get("added_lines") or []:
                if rule.evidence.search(line):
                    evidence.append({"path": path, "how": ch["change"], "line": line[:140]})
                    break
        if rule.path_evidence and ch["change"] == "added" and rule.path_evidence.search(path):
            evidence.append({"path": path, "how": "added_file"})
        if len(evidence) >= 4:
            break
    return evidence


def _asset_relevant(rule: _Rule, path: str) -> bool:
    p = path.lower()
    if rule.id == "audio":
        return any(p.endswith(e) for e in (".wav", ".mp3", ".ogg")) or "sound" in p
    if rule.id == "ui_visual":
        return any(p.endswith(e) for e in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".ttf", ".otf"))
    return False


def evaluate_claims(claims: Sequence[Dict[str, Any]], diff: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_id = {r.id: r for r in _RULES}
    results: List[Dict[str, Any]] = []
    for claim in claims:
        rule = by_id[claim["id"]]
        ev = _link_claim(rule, diff.get("changes") or [])
        results.append({**claim, "supported": bool(ev), "evidence": ev})
    return results


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def _resolve_root(paths: Sequence[str]) -> Optional[Path]:
    try:
        from app.evidence_completeness_gate import _bounded_submission_root

        for raw in paths:
            if raw and Path(raw).exists():
                return _bounded_submission_root(raw)
    except Exception:
        return None
    return None


_CACHE: Dict[Tuple[str, str], Dict[str, Any]] = {}
_CACHE_MAX = 32


def evaluate_m3_code_diff(
    paths: Sequence[str],
    student_text: str = "",
    *,
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Locate V1/V2, diff them, and link improvement claims to real changes.

    The gate runs on every result/report read path, so identical inputs are cached.
    """
    base = Path(root) if root else _resolve_root(paths)
    key = (str(base), hashlib.sha1((student_text or "").encode("utf-8", "ignore")).hexdigest())
    if base is not None and key in _CACHE:
        return _CACHE[key]
    report = _evaluate_m3_code_diff_uncached(base, student_text)
    if base is not None:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = report
    return report


def _evaluate_m3_code_diff_uncached(base: Optional[Path], student_text: str) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "version": CODE_DIFF_VERSION,
        "evaluated": True,
        "ok": False,
        "status": "versions_not_found",
        "v1_root": None,
        "v2_root": None,
        "substantive_change_count": 0,
        "claims": [],
        "supported_claims": 0,
        "unsupported_claims": [],
        "claims_total": 0,
    }
    if base is None:
        report["status"] = "no_submission_root"
        return report
    groups = discover_version_groups(base)
    report["status"] = groups["status"]
    if groups["status"] != "ok":
        return report
    v1, v2 = groups["v1"], groups["v2"]
    report["v1_root"] = str(v1["project_root"])
    report["v2_root"] = str(v2["project_root"])
    diff = compute_code_diff(v1, v2)
    report["files_v1"], report["files_v2"] = diff["files_v1"], diff["files_v2"]
    report["substantive_change_count"] = diff["substantive_change_count"]
    report["changed_files"] = [
        {"path": c["path"], "change": c["change"], "kind": c["kind"],
         "added": len(c.get("added_lines") or []), "removed": len(c.get("removed_lines") or [])}
        for c in diff["changes"][:60]
    ]
    if diff["substantive_change_count"] == 0:
        report["status"] = "no_code_change"
        return report

    claims = extract_improvement_claims(student_text)
    results = evaluate_claims(claims, diff)
    supported = [c for c in results if c["supported"]]
    report["claims"] = results
    report["claims_total"] = len(results)
    report["supported_claims"] = len(supported)
    report["unsupported_claims"] = [c["label"] for c in results if not c["supported"]]
    if not results:
        report["status"] = "no_claims_to_link"
        return report
    ratio = len(supported) / len(results)
    report["supported_ratio"] = round(ratio, 2)
    if len(supported) >= MIN_SUPPORTED_CLAIMS and ratio >= MIN_SUPPORTED_RATIO:
        report["ok"] = True
        report["status"] = "supported"
    else:
        report["status"] = "improvements_mostly_unsupported"
    return report
