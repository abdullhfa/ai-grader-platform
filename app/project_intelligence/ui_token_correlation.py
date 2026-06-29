"""
Lightweight UI token correlation across OCR and runtime logs (no LLM).

Deterministic regex anchors only — diagnostics / calibration; does not affect achieved.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .temporal_alignment import parse_timestamp_from_line

TOKEN_CORRELATION_VERSION = "1.0"
_MAX_LOG_LINES = 400

UI_TOKENS: Set[str] = {
    "score",
    "health",
    "hp",
    "ammo",
    "coins",
    "inventory",
    "level",
    "timer",
    "pause",
    "gameover",
}

# Single-source hits on these are flagged as low-anchor noise.
GENERIC_UI_TOKENS: Set[str] = {"pause", "timer", "level", "gameover"}

# Regex per token: OCR and logs (lowercase not required — re.I).
_TOKEN_PATTERNS: Dict[str, re.Pattern] = {
    "score": re.compile(r"\bscore\b|score\s+update", re.I),
    "health": re.compile(r"\bhealth\b|health\s*changed", re.I),
    "hp": re.compile(r"\bhp\b|hp\s*changed", re.I),
    "ammo": re.compile(r"\bammo\b|ammo\s*count", re.I),
    "coins": re.compile(r"\bcoins?\b|coin\s*count", re.I),
    "inventory": re.compile(r"\binventory\b|inventory\s+opened", re.I),
    "level": re.compile(r"\blevel\b|level\s*up|level\s*:", re.I),
    "timer": re.compile(r"\btimer\b|time\s*left|time\s*:", re.I),
    "pause": re.compile(r"\bpause\b|paused|\bmenu\b", re.I),
    "gameover": re.compile(r"game\s*over|gameover", re.I),
}


def _max_video_ts(runtime_evidence: Mapping[str, Any]) -> float:
    mx = 0.0
    for it in runtime_evidence.get("video_evidence_items") or []:
        if not isinstance(it, dict):
            continue
        try:
            mx = max(mx, float(it.get("timestamp_seconds") or 0.0))
        except (TypeError, ValueError):
            continue
    return mx


def _line_ts(
    line: str,
    *,
    max_video: float,
    file_idx: int,
    line_idx: int,
    n_lines: int,
) -> float:
    parsed = parse_timestamp_from_line(line)
    if parsed is not None:
        return float(parsed)
    if max_video > 0 and n_lines > 1:
        return (line_idx / max(n_lines - 1, 1)) * max_video
    if max_video > 0:
        return 0.5 * file_idx + float(line_idx) * 0.01
    return float(file_idx) * 10_000.0 + float(line_idx)


def _scan_logs_for_tokens(
    runtime_evidence: Mapping[str, Any],
) -> Dict[str, List[Tuple[float, str]]]:
    """token -> list of (timestamp_seconds, log_basename)"""
    hits: Dict[str, List[Tuple[float, str]]] = {t: [] for t in UI_TOKENS}
    mv = _max_video_ts(runtime_evidence)
    file_idx = 0
    for row in runtime_evidence.get("log_files") or []:
        if not isinstance(row, dict):
            continue
        pth = row.get("path")
        base = str(row.get("basename") or "")
        if not pth:
            continue
        try:
            raw = Path(str(pth)).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = [ln for ln in raw.splitlines() if ln.strip()][: _MAX_LOG_LINES]
        n = len(lines)
        for i, ln in enumerate(lines):
            ts = _line_ts(ln, max_video=mv, file_idx=file_idx, line_idx=i, n_lines=n)
            for tok in UI_TOKENS:
                if _TOKEN_PATTERNS[tok].search(ln):
                    hits[tok].append((round(ts, 4), base))
        file_idx += 1
    return hits


def _scan_ocr_for_tokens(
    runtime_evidence: Mapping[str, Any],
) -> Dict[str, List[Tuple[float, str]]]:
    hits: Dict[str, List[Tuple[float, str]]] = {t: [] for t in UI_TOKENS}
    for row in runtime_evidence.get("ocr_evidence_items") or []:
        if not isinstance(row, dict):
            continue
        if row.get("evidence_type") != "ocr_text":
            continue
        try:
            ts = float(row.get("timestamp_seconds") or 0.0)
        except (TypeError, ValueError):
            continue
        raw = str(row.get("raw_text") or "")
        src = str(row.get("source") or "ocr")
        for tok in UI_TOKENS:
            if _TOKEN_PATTERNS[tok].search(raw):
                hits[tok].append((round(ts, 4), src))
    return hits


def _times_overlap(
    ocr_ts: Sequence[Tuple[float, str]],
    log_ts: Sequence[Tuple[float, str]],
    window_sec: float,
) -> bool:
    if not ocr_ts or not log_ts:
        return False
    for ot, _ in ocr_ts:
        for lt, __ in log_ts:
            if abs(float(ot) - float(lt)) <= window_sec:
                return True
    return False


def _correlation_strength(sources: List[str], temporal_overlap: bool) -> str:
    if len(sources) < 2:
        return "weak"
    if temporal_overlap:
        return "strong"
    return "medium"


def _build_token_groups(
    ocr_hits: Mapping[str, List[Tuple[float, str]]],
    log_hits: Mapping[str, List[Tuple[float, str]]],
    window_sec: float,
) -> List[Dict[str, Any]]:
    groups: List[Dict[str, Any]] = []
    for tok in sorted(UI_TOKENS):
        oh = ocr_hits.get(tok) or []
        lh = log_hits.get(tok) or []
        if not oh and not lh:
            continue
        sources: List[str] = []
        if oh:
            sources.append("ocr_text")
        if lh:
            sources.append("runtime_log")
        overlap = _times_overlap(oh, lh, window_sec)
        groups.append(
            {
                "token": tok,
                "sources": sources,
                "temporal_overlap": overlap,
                "correlation_strength": _correlation_strength(sources, overlap),
                "ocr_hit_count": len(oh),
                "runtime_log_hit_count": len(lh),
            }
        )
    return groups


def _build_noise_flags(groups: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    flags: List[Dict[str, str]] = []
    for g in groups:
        tok = str(g.get("token") or "")
        srcs = g.get("sources") or []
        overlap = bool(g.get("temporal_overlap"))
        strength = str(g.get("correlation_strength") or "weak")
        if len(srcs) >= 2 and not overlap:
            flags.append(
                {"flag": "token_without_temporal_support", "detail": tok}
            )
        if len(srcs) == 1 and tok in GENERIC_UI_TOKENS:
            flags.append({"flag": "generic_ui_token_only", "detail": tok})
    return flags


def _dedupe_flags(flags: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: Set[Tuple[str, str]] = set()
    out: List[Dict[str, str]] = []
    for f in flags:
        key = (str(f.get("flag")), str(f.get("detail")))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def _build_reasoning(groups: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    reasons: Set[str] = set()
    any_overlap = False
    for g in groups:
        tok = str(g.get("token") or "")
        srcs = set(g.get("sources") or [])
        if "ocr_text" in srcs:
            reasons.add(f"{tok}_detected_in_ocr_text")
        if "runtime_log" in srcs:
            reasons.add(f"{tok}_detected_in_runtime_log")
        if bool(g.get("temporal_overlap")):
            any_overlap = True
    if any_overlap:
        reasons.add("token_overlap_within_same_temporal_window")
    return {"reasoning": sorted(reasons)}


def build_ui_token_correlation(profile: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """
    Correlate UI_TOKENS between OCR and runtime logs with simple temporal proximity.
    """
    if not profile or not isinstance(profile.get("runtime_evidence"), dict):
        return {
            "version": TOKEN_CORRELATION_VERSION,
            "window_seconds": None,
            "token_correlation_groups": [],
            "token_noise_flags": [],
            "token_reasoning": {"reasoning": []},
        }

    rt = profile["runtime_evidence"]
    if not isinstance(rt, dict):
        rt = {}

    ta = profile.get("temporal_alignment") or {}
    window_sec = 5.0
    if isinstance(ta, dict):
        try:
            window_sec = float(ta.get("window_seconds") or 5.0)
        except (TypeError, ValueError):
            window_sec = 5.0

    ocr_hits = _scan_ocr_for_tokens(rt)
    log_hits = _scan_logs_for_tokens(rt)
    groups = _build_token_groups(ocr_hits, log_hits, window_sec)
    noise = _dedupe_flags(_build_noise_flags(groups))
    reasoning = _build_reasoning(groups)

    return {
        "version": TOKEN_CORRELATION_VERSION,
        "window_seconds": window_sec,
        "token_correlation_groups": groups,
        "token_noise_flags": noise,
        "token_reasoning": reasoning,
    }
