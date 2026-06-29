"""Timeline presenter — MM:SS labels, confidence coloring, contradiction markers."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.governance.replay_viewer import ReplayInspectionBundle

CONTRADICTION_TYPES = frozenset({"runtime_vs_gameplay", "contradiction", "conflict"})


def _format_ts(seconds: float) -> str:
    total = max(0, int(seconds))
    mm, ss = divmod(total, 60)
    return f"{mm:02d}:{ss:02d}"


def _confidence_class(confidence: float) -> str:
    if confidence >= 0.8:
        return "conf-high"
    if confidence >= 0.5:
        return "conf-mid"
    return "conf-low"


def _extract_events(bundle: ReplayInspectionBundle) -> List[Dict[str, Any]]:
    timeline = bundle.timeline or {}
    if isinstance(timeline, dict):
        events = timeline.get("events") or []
        if events:
            return events
    gameplay = bundle.ai_reasoning.get("validation", {}).get("timeline") if bundle.ai_reasoning else None
    if isinstance(gameplay, dict):
        return gameplay.get("events") or []
    return []


def present_timeline(bundle: ReplayInspectionBundle) -> Dict[str, Any]:
    raw_events = _extract_events(bundle)
    contradiction_ts: set[float] = set()
    for c in bundle.contradictions or []:
        if isinstance(c, dict) and c.get("timestamp") is not None:
            try:
                contradiction_ts.add(float(c["timestamp"]))
            except (TypeError, ValueError):
                pass

    rows: List[Dict[str, Any]] = []
    for ev in raw_events:
        if not isinstance(ev, dict):
            continue
        ts = float(ev.get("timestamp") or ev.get("t") or 0)
        conf = float(ev.get("confidence") or 0.5)
        etype = str(ev.get("type") or ev.get("label") or "event")
        severity = str(ev.get("severity") or "info")
        is_contra = (
            etype in CONTRADICTION_TYPES
            or severity == "contradiction"
            or any(abs(ts - ct) < 0.5 for ct in contradiction_ts)
        )
        rows.append({
            "timestamp": ts,
            "time_label": _format_ts(ts),
            "type": etype,
            "confidence": conf,
            "confidence_pct": int(conf * 100),
            "confidence_class": _confidence_class(conf),
            "severity": severity,
            "source": ev.get("source") or "gameplay",
            "contradiction": is_contra,
            "replay_link": f"#screenshot-{int(ts)}",
            "display_line": f"{_format_ts(ts)} {etype}",
        })

    rows.sort(key=lambda r: r["timestamp"])
    summary_lines = [r["display_line"] + (f" ({r['confidence']:.2f})" if r["confidence"] else "") for r in rows]

    return {
        "event_count": len(rows),
        "duration_seconds": max((r["timestamp"] for r in rows), default=0),
        "events": rows,
        "summary_lines": summary_lines,
        "contradiction_count": sum(1 for r in rows if r["contradiction"]),
    }
