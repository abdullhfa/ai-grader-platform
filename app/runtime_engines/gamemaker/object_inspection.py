"""GameMaker object/resource inspection — sprites, rooms, events, objects."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.runtime_engines.gamemaker.project_probe import GameMakerLayout, load_yyp_metadata

_EVENT_RE = re.compile(r"^([A-Za-z]+)_(\d+)\.gml$", re.IGNORECASE)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _resource_names_from_yyp(yyp_path: Path) -> Dict[str, List[str]]:
    data = _read_json(yyp_path) or {}
    buckets: Dict[str, List[str]] = {
        "objects": [],
        "sprites": [],
        "rooms": [],
        "scripts": [],
        "sounds": [],
        "other": [],
    }
    for res in data.get("resources") or []:
        if not isinstance(res, dict):
            continue
        rtype = str(res.get("resourceType") or "")
        name = ""
        rid = res.get("id")
        if isinstance(rid, dict):
            name = str(rid.get("name") or "")
        if not name:
            continue
        if "Object" in rtype:
            buckets["objects"].append(name)
        elif "Sprite" in rtype:
            buckets["sprites"].append(name)
        elif "Room" in rtype:
            buckets["rooms"].append(name)
        elif "Script" in rtype:
            buckets["scripts"].append(name)
        elif "Sound" in rtype:
            buckets["sounds"].append(name)
        else:
            buckets["other"].append(name)
    return buckets


def _scan_resource_tree(project_root: Path) -> Dict[str, Any]:
    objects: List[Dict[str, Any]] = []
    sprites: List[str] = []
    rooms: List[str] = []
    events: List[Dict[str, Any]] = []

    obj_root = project_root / "objects"
    if obj_root.is_dir():
        for obj_dir in sorted(obj_root.iterdir()):
            if not obj_dir.is_dir():
                continue
            obj_events: List[str] = []
            for gml in sorted(obj_dir.glob("*.gml")):
                m = _EVENT_RE.match(gml.name)
                label = f"{m.group(1)}_{m.group(2)}" if m else gml.stem
                obj_events.append(label)
                events.append(
                    {
                        "object": obj_dir.name,
                        "event": label,
                        "file": str(gml),
                    }
                )
            yy_meta = _read_json(obj_dir / f"{obj_dir.name}.yy") or {}
            objects.append(
                {
                    "name": obj_dir.name,
                    "event_count": len(obj_events),
                    "events": obj_events[:12],
                    "sprite_id": (yy_meta.get("spriteId") or {}).get("name") if isinstance(yy_meta.get("spriteId"), dict) else None,
                }
            )

    spr_root = project_root / "sprites"
    if spr_root.is_dir():
        sprites = sorted(d.name for d in spr_root.iterdir() if d.is_dir())

    room_root = project_root / "rooms"
    if room_root.is_dir():
        rooms = sorted(d.name for d in room_root.iterdir() if d.is_dir())

    return {
        "objects": objects,
        "sprites": sprites,
        "rooms": rooms,
        "events": events,
        "object_count": len(objects),
        "sprite_count": len(sprites),
        "room_count": len(rooms),
        "event_count": len(events),
    }


def inspect_gamemaker_objects(layout: GameMakerLayout) -> Dict[str, Any]:
    """Extract sprites, rooms, events, objects from YYP + on-disk tree."""
    project_root = layout.project_root
    if layout.yyp_path:
        project_root = layout.yyp_path.parent

    result: Dict[str, Any] = {
        "version": "gamemaker_object_inspection_v1",
        "yyp_metadata": load_yyp_metadata(layout.yyp_path) if layout.yyp_path else {"ok": False},
        "yyp_resources": {},
        "filesystem_tree": {},
        "gml_file_count": len(layout.gml_files),
    }

    if layout.yyp_path and layout.yyp_path.is_file():
        result["yyp_resources"] = _resource_names_from_yyp(layout.yyp_path)

    if project_root and project_root.is_dir():
        result["filesystem_tree"] = _scan_resource_tree(project_root)

    tree = result["filesystem_tree"]
    yyp_res = result["yyp_resources"]
    result["summary"] = {
        "objects": max(tree.get("object_count", 0), len(yyp_res.get("objects") or [])),
        "sprites": max(tree.get("sprite_count", 0), len(yyp_res.get("sprites") or [])),
        "rooms": max(tree.get("room_count", 0), len(yyp_res.get("rooms") or [])),
        "events": tree.get("event_count", 0),
        "scripts": len(yyp_res.get("scripts") or []),
    }
    result["inspection_ok"] = (
        result["summary"]["objects"] > 0
        or result["summary"]["rooms"] > 0
        or result["gml_file_count"] > 0
    )
    return result
