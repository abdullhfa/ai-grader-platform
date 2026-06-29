"""GameMaker artifact analysis — no IDE automation."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.runtime_engines.gamemaker.project_probe import GameMakerLayout, load_yyp_metadata


def _summarize_gml(gml_files: List[Path], limit: int = 12) -> Dict[str, Any]:
    samples: List[Dict[str, Any]] = []
    total_lines = 0
    event_map: Dict[str, int] = {}
    keywords = {
        "keyboard": 0,
        "collision": 0,
        "draw": 0,
        "step": 0,
        "score": 0,
        "room": 0,
    }
    for fp in gml_files[:limit]:
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.count("\n") + 1
        total_lines += lines
        lower = text.lower()
        for key in keywords:
            if key in lower:
                keywords[key] += 1
        event_hint = fp.stem.split("_")[0] if "_" in fp.stem else fp.stem
        event_map[event_hint] = event_map.get(event_hint, 0) + 1
        samples.append({"path": str(fp), "lines": lines, "object_hint": fp.parent.name, "event_hint": event_hint})
    complexity = min(1.0, 0.2 + (len(gml_files) * 0.05) + (total_lines / 500.0))
    return {
        "sample_count": len(samples),
        "total_lines_sampled": total_lines,
        "keyword_hits": keywords,
        "event_mapping": event_map,
        "complexity_estimate": round(complexity, 3),
        "samples": samples,
    }


def analyze_gamemaker_artifacts(layout: GameMakerLayout) -> Dict[str, Any]:
    """Static project analysis when no runnable build is available."""
    result: Dict[str, Any] = {
        "mode": "artifact_analysis",
        "layout": layout.to_dict(),
        "runnable_build_present": bool(layout.executable or layout.html_entry),
    }

    if layout.yyp_path:
        result["yyp_metadata"] = load_yyp_metadata(layout.yyp_path)
        result["resource_count"] = result["yyp_metadata"].get("resource_count", 0)

    if layout.gml_files:
        result["gml_analysis"] = _summarize_gml(layout.gml_files)

    result["project_graph"] = _project_graph(layout.project_root or layout.yyp_path.parent if layout.yyp_path else None)
    result["completeness_hint"] = _completeness_score(result)
    return result


def _project_graph(project_root: Optional[Path]) -> Dict[str, Any]:
    """Room/object graph hints for static GameMaker inference."""
    if not project_root or not project_root.is_dir():
        return {"object_count": 0, "room_count": 0, "event_files": 0}

    object_dirs = [p for p in project_root.rglob("objects") if p.is_dir() and p.name.lower() == "objects"]
    room_dirs = [p for p in project_root.rglob("rooms") if p.is_dir() and p.name.lower() == "rooms"]
    event_files = 0
    for obj_root in object_dirs[:3]:
        for gml in obj_root.rglob("*.gml"):
            event_files += 1
            if event_files >= 50:
                break

    return {
        "object_count": sum(1 for _ in (object_dirs[0].iterdir() if object_dirs else [])),
        "room_count": sum(1 for _ in (room_dirs[0].iterdir() if room_dirs else [])),
        "event_files": event_files,
        "has_objects_tree": bool(object_dirs),
        "has_rooms_tree": bool(room_dirs),
    }


def _completeness_score(analysis: Dict[str, Any]) -> float:
    score = 0.35
    if analysis.get("yyp_metadata", {}).get("ok"):
        score += 0.25
    gml = analysis.get("gml_analysis") or {}
    if gml.get("sample_count", 0) >= 3:
        score += 0.20
    if analysis.get("runnable_build_present"):
        score += 0.20
    return min(1.0, score)
