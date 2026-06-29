"""
Unity — semantic gameplay / structure analysis (Phase 2).

Heuristic static analysis of student-submitted Unity C# (and light YAML peeks).
Goals:
- Reduce false positives vs bare pattern matching (empty callbacks, name-only classes).
- Attach confidence, evidence_count, and execution_evidence per subsystem signal.

This is not play-mode verification; limitations are returned for the LLM rubric.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_CS = ".cs"
_UNITY_ASSET = ".unity"
_PREFAB = ".prefab"

# Lifecycle / physics callbacks — require non-trivial body for "strong" collision signal
_COLLISION_SIGS = (
    "OnCollisionEnter",
    "OnCollisionStay",
    "OnCollisionExit",
    "OnTriggerEnter",
    "OnTriggerStay",
    "OnTriggerExit",
    "OnCollisionEnter2D",
    "OnCollisionStay2D",
    "OnCollisionExit2D",
    "OnTriggerEnter2D",
    "OnTriggerStay2D",
    "OnTriggerExit2D",
)

_MONO_RE = re.compile(
    r"\bclass\s+(\w+)\s*:\s*([\w.<>,\s]+)\b",
    re.MULTILINE,
)
_USING_RE = re.compile(r"^\s*using\s+([\w.]+)\s*;", re.MULTILINE)
_SERIALIZE_RE = re.compile(r"\[SerializeField\]")


def _strip_c_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"//.*?$", " ", text, flags=re.MULTILINE)
    return text


def _first_brace_block_after(src: str, start: int) -> Optional[Tuple[int, int]]:
    """Find first '{' at or after start and return (open_idx, close_idx) inclusive."""
    i = src.find("{", start)
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(src)):
        c = src[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return (i, j)
    return None


def _body_strength(body: str) -> Tuple[int, str]:
    """
    Returns (score 0..n, execution_evidence: weak|medium|strong).
    """
    b = _strip_c_comments(body)
    b = re.sub(r"\s+", " ", b).strip()
    if len(b) <= 2:
        return (0, "weak")

    inner = b[1:-1] if b.startswith("{") and b.endswith("}") else b
    inner = inner.strip()
    if not inner or inner in (";",):
        return (0, "weak")

    # Trivial: only base.Method(), Debug.Log, or empty try
    trivial_only = re.match(
        r"^\s*(base\.\w+\s*\([^)]*\)\s*;|Debug\.Log\([^;]*\)\s*;?)\s*$",
        inner,
        re.IGNORECASE,
    )
    if trivial_only:
        return (1, "weak")

    score = 0
    if re.search(r"\b(if|else|for|foreach|while|switch|case|return)\b", inner):
        score += 2
    if re.search(r"[+=\-*/]=|\+\+|\-\-", inner):
        score += 1
    if len(re.findall(r"\.", inner)) >= 4:
        score += 1
    unity_calls = len(
        re.findall(
            r"\b(Destroy|Instantiate|GetComponent|GetComponentInChildren|"
            r"Rigidbody2D|Rigidbody|AddForce|transform|Time\.deltaTime|"
            r"Collision2D|Collider2D|Animator|PlayerPrefs)\b",
            inner,
        )
    )
    score += min(4, unity_calls)

    if score <= 1:
        ev = "weak"
    elif score <= 4:
        ev = "medium"
    else:
        ev = "strong"
    return (score, ev)


def _collect_monobehaviours(text: str, rel_path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in _MONO_RE.finditer(text):
        name, bases = m.group(1), m.group(2)
        bases_clean = re.sub(r"\s+", " ", bases).strip()
        if "MonoBehaviour" not in bases_clean:
            continue
        out.append(
            {
                "class": name,
                "file": rel_path,
                "bases": bases_clean[:120],
                "has_serialize_fields": bool(_SERIALIZE_RE.search(text)),
            }
        )
    return out


def _find_callback_evidences(
    text: str, rel_path: str, signatures: Tuple[str, ...]
) -> List[Dict[str, Any]]:
    ev: List[Dict[str, Any]] = []
    clean_for_search = text
    for sig in signatures:
        pat = re.compile(rf"\bvoid\s+{re.escape(sig)}\s*\([^)]*\)\s*")
        for m in pat.finditer(clean_for_search):
            blk = _first_brace_block_after(clean_for_search, m.end())
            if not blk:
                continue
            open_i, close_i = blk
            body = clean_for_search[open_i : close_i + 1]
            score, strength = _body_strength(body)
            line_no = clean_for_search.count("\n", 0, m.start()) + 1
            ev.append(
                {
                    "callback": sig,
                    "file": rel_path,
                    "line": line_no,
                    "body_score": score,
                    "execution_evidence": strength,
                }
            )
    return ev


def _inventory_evidence(text: str, rel_path: str) -> List[Dict[str, Any]]:
    ev: List[Dict[str, Any]] = []
    if not re.search(r"\b(class|interface)\s+\w*Inventory\w*\b", text, re.I):
        return ev
    for m in re.finditer(
        r"\b(public|private|protected)\s+[\w.<>\[\]]+\s+(Add|Remove|Use|Drop)?Item\w*\s*\(",
        text,
    ):
        p0 = m.end() - 1
        if p0 < 0 or text[p0] != "(":
            continue
        depth = 0
        rp = -1
        for i in range(p0, min(len(text), p0 + 4000)):
            c = text[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    rp = i
                    break
        if rp < 0:
            continue
        blk = _first_brace_block_after(text, rp + 1)
        if not blk:
            continue
        body = text[blk[0] : blk[1] + 1]
        score, strength = _body_strength(body)
        if score >= 2 or strength != "weak":
            line_no = text.count("\n", 0, m.start()) + 1
            ev.append(
                {
                    "kind": "inventory_method",
                    "file": rel_path,
                    "line": line_no,
                    "body_score": score,
                    "execution_evidence": strength,
                }
            )
    return ev


def _scalar_signals(text: str, rel_path: str) -> Dict[str, List[str]]:
    """Pattern hits with line context (not yet body-verified)."""
    found: Dict[str, List[str]] = {}
    lines = text.splitlines()

    def add(key: str, msg: str) -> None:
        found.setdefault(key, []).append(msg)

    for i, line in enumerate(lines, 1):
        L = line.strip()
        if re.search(r"\bInput\.(GetKey|GetButton|GetAxis|GetMouseButton)\b", L):
            add("input_system", f"{rel_path}:{i} Input API")
        if re.search(r"\b(AudioSource|AudioClip)\b", L):
            add("audio_system", f"{rel_path}:{i} audio type")
        if re.search(r"\b(Canvas|UnityEngine\.UI\.|Button|TextMeshProUGUI)\b", L):
            add("ui_system", f"{rel_path}:{i} UI type")
        if re.search(r"\b(Animator|AnimationClip|SetTrigger|SetBool)\b", L):
            add("animation_system", f"{rel_path}:{i} animation API")
        if re.search(r"\b(PlayerPrefs|JsonUtility|Save|Load)\b", L):
            if re.search(r"\b(PlayerPrefs|JsonUtility)\b", L):
                add("save_system", f"{rel_path}:{i} persistence API")
        if re.search(r"\b(NavMeshAgent|NavMesh)\b", L):
            add("enemy_ai", f"{rel_path}:{i} NavMesh")
        if re.search(r"\b(Rigidbody2D|Rigidbody)\b", L):
            add("physics_system", f"{rel_path}:{i} Rigidbody")
    return found


def _confidence_from_evidences(
    evidences: List[Dict[str, Any]], base: float = 0.35
) -> float:
    if not evidences:
        return 0.0
    strong = sum(1 for e in evidences if e.get("execution_evidence") == "strong")
    med = sum(1 for e in evidences if e.get("execution_evidence") == "medium")
    weak = sum(1 for e in evidences if e.get("execution_evidence") == "weak")
    score = base + 0.25 * strong + 0.12 * med + 0.04 * min(weak, 2)
    return round(min(0.95, score), 2)


def _yaml_script_hints(text: str, rel_path: str) -> List[str]:
    """Very light peek: YAML lines mentioning scripts / prefab linkage."""
    hints: List[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        if "m_Script:" in line or "guid:" in line or "prefab" in line.lower():
            if "m_Script:" in line or "MonoBehaviour" in line:
                hints.append(f"{rel_path}:{i} asset reference")
        if len(hints) >= 30:
            break
    return hints[:15]


def analyze_unity_submission(file_paths: List[Path]) -> Dict[str, Any]:
    """
    Run semantic Unity analysis on resolved file paths.
    """
    cs_files = [p for p in file_paths if p.suffix.lower() == _CS]
    asset_files = [p for p in file_paths if p.suffix.lower() in (_UNITY_ASSET, _PREFAB)]

    monobehaviours: List[Dict[str, Any]] = []
    collision_evs: List[Dict[str, Any]] = []
    inventory_evs: List[Dict[str, Any]] = []
    scalar_hits: Dict[str, List[str]] = {}
    usings: List[str] = []
    yaml_hints: List[str] = []

    for p in sorted(set(cs_files), key=lambda x: str(x).lower()):
        try:
            raw = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = p.name

        monobehaviours.extend(_collect_monobehaviours(raw, rel))
        collision_evs.extend(_find_callback_evidences(raw, rel, _COLLISION_SIGS))
        inventory_evs.extend(_inventory_evidence(raw, rel))
        for k, v in _scalar_signals(raw, rel).items():
            scalar_hits.setdefault(k, []).extend(v)
        usings.extend(_USING_RE.findall(raw))

    for p in sorted(set(asset_files), key=lambda x: str(x).lower())[:8]:
        try:
            raw = p.read_text(encoding="utf-8", errors="ignore")[:200_000]
        except OSError:
            continue
        rel = p.name
        yaml_hints.extend(_yaml_script_hints(raw, rel))

    system_detections: List[Dict[str, Any]] = []

    if collision_evs:
        non_weak = [e for e in collision_evs if e.get("execution_evidence") != "weak"]
        use = non_weak if non_weak else collision_evs
        conf = _confidence_from_evidences(use, base=0.3)
        if not non_weak:
            conf = min(conf, 0.45)
        ev_strings = [
            f"{e['file']}:{e['line']} {e['callback']} ({e['execution_evidence']})"
            for e in use[:8]
        ]
        system_detections.append(
            {
                "system": "collision_system",
                "confidence": conf,
                "evidence_count": len(collision_evs),
                "execution_evidence": (
                    "strong"
                    if any(e["execution_evidence"] == "strong" for e in use)
                    else (
                        "medium"
                        if any(e["execution_evidence"] == "medium" for e in use)
                        else "weak"
                    )
                ),
                "evidence": ev_strings,
            }
        )

    if inventory_evs:
        system_detections.append(
            {
                "system": "inventory_system",
                "confidence": _confidence_from_evidences(inventory_evs, base=0.4),
                "evidence_count": len(inventory_evs),
                "execution_evidence": max(
                    (e["execution_evidence"] for e in inventory_evs),
                    key=lambda x: {"weak": 0, "medium": 1, "strong": 2}.get(x, 0),
                ),
                "evidence": [
                    f"{e['file']}:{e['line']} inventory method ({e['execution_evidence']})"
                    for e in inventory_evs[:6]
                ],
            }
        )

    # Scalar-based systems (lower default confidence)
    for sys_key, hits in scalar_hits.items():
        if sys_key == "physics_system" and any(
            s["system"] == "collision_system" for s in system_detections
        ):
            continue
        if not hits:
            continue
        uniq = hits[:10]
        conf = min(0.72, 0.35 + 0.04 * len(uniq))
        system_detections.append(
            {
                "system": sys_key,
                "confidence": round(conf, 2),
                "evidence_count": len(hits),
                "execution_evidence": "medium" if len(hits) >= 3 else "weak",
                "evidence": uniq,
            }
        )

    return {
        "extractor_version": 2,
        "scripts_analyzed": len(cs_files),
        "assets_peeked": len(asset_files),
        "monobehaviours": monobehaviours[:40],
        "monobehaviour_count": len(monobehaviours),
        "system_detections": system_detections,
        "using_namespaces_top": sorted(
            {u for u in usings if u.startswith("UnityEngine")}
        )[:20],
        "scene_prefab_hints": yaml_hints[:15],
        "limitations_ar": (
            "تحليل ساكن للنص فقط: لا يثبت ارتباط المكوّنات بالمشهد ولا تنفيذ اللعب في المحاكي؛ "
            "الثقة تعكس عمق أجسام الدوال وليس اختبار تشغيل."
        ),
    }
