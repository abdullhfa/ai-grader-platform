"""
Deterministic temporal alignment of runtime evidence (no LLM).

Clusters video_frame, OCR text, runtime screenshot, and log-line events into time
windows for diagnostics and calibration only — not used for final achieved/grade.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

ALIGNMENT_VERSION = "1.0"
DEFAULT_WINDOW_SECONDS = 5.0
_MAX_LOG_LINES_PER_FILE = 400

_LINE_TS_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("t_equals", re.compile(r"\bt\s*[=:]\s*(\d+\.?\d*)\b", re.I)),
    ("bracket_num", re.compile(r"\[\s*(\d+\.?\d*)\s*\]")),
    ("leading_float", re.compile(r"^\s*(\d+\.?\d+)\s+")),
    ("hms", re.compile(r"\b(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d+))?\b")),
)

_FILENAME_TS = re.compile(
    r"(?:_|^|\b)t\s*(\d+\.?\d*)s?\b|(\d+)s(?=\.|$)|shot_(\d+\.?\d*)|frame_(\d+\.?\d*)",
    re.I,
)

_COLLISION_HINT = re.compile(
    r"\b(oncollisionenter|oncollisionexit|ontriggerenter|ontriggerexit|"
    r"oncollision|ontrigger|collision|trigger_enter|collision_enter)\b",
    re.I,
)


def _parse_hms_to_seconds(m: re.Match) -> float:
    h, mnt, s, frac = m.group(1), m.group(2), m.group(3), m.group(4)
    base = int(h) * 3600 + int(mnt) * 60 + int(s)
    if frac:
        base += int(frac[:3].ljust(3, "0")) / 1000.0
    return float(base)


def parse_timestamp_from_line(line: str) -> Optional[float]:
    s = line.strip()
    if not s:
        return None
    for name, pat in _LINE_TS_PATTERNS:
        m = pat.search(s)
        if not m:
            continue
        if name == "hms":
            try:
                return _parse_hms_to_seconds(m)
            except (TypeError, ValueError):
                continue
        try:
            return float(m.group(1))
        except (TypeError, ValueError, IndexError):
            continue
    return None


def parse_timestamp_from_screenshot_path(path: str, basename: str) -> Optional[float]:
    blob = f"{path}\n{basename}"
    m = _FILENAME_TS.search(blob)
    if not m:
        return None
    for g in m.groups():
        if g is not None:
            try:
                return float(g)
            except ValueError:
                continue
    return None


def classify_log_line_key(line: str) -> str:
    if _COLLISION_HINT.search(line):
        return "runtime_log_collision"
    return "runtime_log_generic"


def _max_video_timestamp(runtime_evidence: Mapping[str, Any]) -> float:
    mx = 0.0
    for it in runtime_evidence.get("video_evidence_items") or []:
        if not isinstance(it, dict):
            continue
        try:
            mx = max(mx, float(it.get("timestamp_seconds") or 0.0))
        except (TypeError, ValueError):
            continue
    return mx


def _extract_log_line_events(runtime_evidence: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    mv = _max_video_timestamp(runtime_evidence)
    file_idx = 0
    for row in runtime_evidence.get("log_files") or []:
        if not isinstance(row, dict):
            continue
        pth = row.get("path")
        base = row.get("basename") or ""
        if not pth:
            continue
        try:
            raw = Path(str(pth)).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = [ln for ln in raw.splitlines() if ln.strip()][: _MAX_LOG_LINES_PER_FILE]
        n = len(lines)
        for i, ln in enumerate(lines):
            ts = parse_timestamp_from_line(ln)
            if ts is None:
                if mv > 0 and n > 1:
                    ts = (i / max(n - 1, 1)) * mv
                elif mv > 0:
                    ts = 0.5 * file_idx + float(i) * 0.01
                else:
                    ts = float(file_idx) * 10_000.0 + float(i) * 1.0
            ek = classify_log_line_key(ln)
            out.append(
                {
                    "timestamp_seconds": round(float(ts), 4),
                    "evidence_type": "runtime_log_line",
                    "event_key": ek,
                    "source": str(base),
                    "detail": "synthetic_ts" if parse_timestamp_from_line(ln) is None else "parsed_ts",
                }
            )
        file_idx += 1
    return out


def _screenshot_events(runtime_evidence: Mapping[str, Any], max_video_ts: float) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, row in enumerate(runtime_evidence.get("screenshot_candidates") or []):
        if not isinstance(row, dict):
            continue
        pth = str(row.get("path") or "")
        base = str(row.get("basename") or "")
        ts = parse_timestamp_from_screenshot_path(pth, base)
        if ts is None:
            ts = max_video_ts + 50.0 + float(idx) * 10.0
        out.append(
            {
                "timestamp_seconds": round(float(ts), 4),
                "evidence_type": "runtime_screenshot",
                "event_key": "runtime_screenshot",
                "source": base or Path(pth).name,
                "detail": "filename_ts" if parse_timestamp_from_screenshot_path(pth, base) is not None else "synthetic_ts",
            }
        )
    return out


def _video_events(runtime_evidence: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in runtime_evidence.get("video_evidence_items") or []:
        if not isinstance(row, dict):
            continue
        try:
            ts = float(row.get("timestamp_seconds"))
        except (TypeError, ValueError):
            continue
        src = row.get("source")
        if not src:
            continue
        out.append(
            {
                "timestamp_seconds": round(ts, 4),
                "evidence_type": "video_frame",
                "event_key": "video_frame",
                "source": str(src),
                "detail": "extraction_order",
            }
        )
    return out


def _ocr_events(runtime_evidence: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in runtime_evidence.get("ocr_evidence_items") or []:
        if not isinstance(row, dict):
            continue
        try:
            ts = float(row.get("timestamp_seconds"))
        except (TypeError, ValueError):
            continue
        src = row.get("source")
        if not src:
            continue
        out.append(
            {
                "timestamp_seconds": round(ts, 4),
                "evidence_type": "ocr_text",
                "event_key": "ocr_text",
                "source": str(src),
                "detail": "ocr_presence",
            }
        )
    return out


def _window_strength(event_keys: Set[str]) -> str:
    vf = "video_frame" in event_keys
    shot = "runtime_screenshot" in event_keys
    log = any(k.startswith("runtime_log") for k in event_keys)
    if vf and log and shot:
        return "strong"
    if vf and log:
        return "medium"
    if vf:
        return "weak"
    return "weak"


def _strength_rank(s: str) -> int:
    return {"weak": 0, "medium": 1, "strong": 2}.get(s, 0)


def _build_windows(events: List[Dict[str, Any]], window_sec: float) -> List[Dict[str, Any]]:
    if not events:
        return []
    sorted_e = sorted(events, key=lambda x: float(x["timestamp_seconds"]))
    groups: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = [sorted_e[0]]
    anchor = float(sorted_e[0]["timestamp_seconds"])
    for e in sorted_e[1:]:
        ts = float(e["timestamp_seconds"])
        if ts - anchor <= window_sec:
            cur.append(e)
        else:
            groups.append(cur)
            cur = [e]
            anchor = ts
    groups.append(cur)

    out_win: List[Dict[str, Any]] = []
    for g in groups:
        ts_list = [float(x["timestamp_seconds"]) for x in g]
        w0 = min(ts_list)
        w1 = max(w0 + window_sec, max(ts_list))
        keys = {str(x.get("event_key") or x.get("evidence_type")) for x in g}
        kinds = sorted(keys)
        strength = _window_strength(keys)
        out_win.append(
            {
                "window_start": round(w0, 4),
                "window_end": round(w1, 4),
                "events": kinds,
                "temporal_alignment_strength": strength,
                "event_count": len(g),
            }
        )
    return out_win


def _collect_reasoning(
    windows: List[Dict[str, Any]], window_sec: float
) -> List[str]:
    wint = int(round(window_sec))
    reasons: List[str] = []
    for w in windows:
        kinds = set(w.get("events") or [])
        if "video_frame" in kinds and any(
            k.startswith("runtime_log") for k in kinds
        ):
            reasons.append(
                f"runtime_log_detected_within_{wint}s_of_video_frame_window"
            )
        if "video_frame" in kinds and "runtime_screenshot" in kinds:
            reasons.append("runtime_screenshot_matches_alignment_window")
        if "video_frame" in kinds and "ocr_text" in kinds:
            reasons.append("ocr_text_within_same_temporal_window_as_video_frame")
    return sorted(set(reasons))


def _collect_conflicts(
    events: List[Dict[str, Any]],
    windows: List[Dict[str, Any]],
    window_sec: float,
) -> List[Dict[str, str]]:
    conflicts: List[Dict[str, str]] = []
    vf_ts = [float(e["timestamp_seconds"]) for e in events if e.get("event_key") == "video_frame"]
    log_ts = [
        float(e["timestamp_seconds"])
        for e in events
        if str(e.get("event_key", "")).startswith("runtime_log")
    ]
    shot_ts = [float(e["timestamp_seconds"]) for e in events if e.get("event_key") == "runtime_screenshot"]

    if vf_ts:
        orphan_vf = 0
        for t in vf_ts:
            near_log = any(abs(t - lt) <= window_sec for lt in log_ts)
            near_shot = any(abs(t - st) <= window_sec for st in shot_ts)
            if not near_log and not near_shot:
                orphan_vf += 1
        if orphan_vf > 0:
            conflicts.append(
                {
                    "flag": "video_frames_without_nearby_runtime_activity",
                    "detail": str(orphan_vf),
                }
            )

    if log_ts and vf_ts:
        orphan_log = 0
        for t in log_ts:
            near_vf = any(abs(t - vt) <= window_sec for vt in vf_ts)
            near_shot = any(abs(t - st) <= window_sec for st in shot_ts)
            if not near_vf and not near_shot:
                orphan_log += 1
        if orphan_log > 0:
            conflicts.append(
                {
                    "flag": "runtime_logs_without_temporal_visual_support",
                    "detail": str(orphan_log),
                }
            )
    elif log_ts and not vf_ts and not shot_ts:
        conflicts.append(
            {"flag": "runtime_logs_without_temporal_visual_support", "detail": "no_visual_evidence"}
        )

    return conflicts


def build_temporal_alignment(profile: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """
    Build temporal_event list, fixed-width windows, strength labels, conflicts, reasoning.
    """
    if not profile:
        return {
            "version": ALIGNMENT_VERSION,
            "window_seconds": DEFAULT_WINDOW_SECONDS,
            "temporal_events": [],
            "temporal_groups": [],
            "temporal_alignment_strength": "weak",
            "temporal_alignment_conflicts": [],
            "temporal_reasoning": {"reasoning": []},
        }

    rt = profile.get("runtime_evidence") or {}
    if not isinstance(rt, dict):
        rt = {}

    window_sec = DEFAULT_WINDOW_SECONDS
    max_v = _max_video_timestamp(rt)
    events: List[Dict[str, Any]] = []
    events.extend(_video_events(rt))
    events.extend(_screenshot_events(rt, max_v))
    events.extend(_ocr_events(rt))
    events.extend(_extract_log_line_events(rt))

    temporal_events = [
        {
            "timestamp_seconds": e["timestamp_seconds"],
            "evidence_type": e["evidence_type"],
            "source": e["source"],
            "event_key": e.get("event_key"),
        }
        for e in sorted(events, key=lambda x: float(x["timestamp_seconds"]))
    ]

    windows = _build_windows(events, window_sec)
    best = "weak"
    for w in windows:
        best_st = w.get("temporal_alignment_strength") or "weak"
        if _strength_rank(str(best_st)) > _strength_rank(best):
            best = str(best_st)

    conflicts = _collect_conflicts(events, windows, window_sec)
    reasoning = {"reasoning": _collect_reasoning(windows, window_sec)}

    return {
        "version": ALIGNMENT_VERSION,
        "window_seconds": window_sec,
        "temporal_events": temporal_events,
        "temporal_groups": windows,
        "temporal_alignment_strength": best,
        "temporal_alignment_conflicts": conflicts,
        "temporal_reasoning": reasoning,
    }
