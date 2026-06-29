"""Tests for PRO Scratch runtime verification."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.grading_mode_policy import deep_grading_flags, fast_grading_flags
from app.runtime_engines.registry import resolve_engine
from app.runtime_engines.scratch.graph_builder import analyze_graph_nodes, build_execution_graph
from app.runtime_engines.scratch.runtime_verification import run_scratch_static_graph
from app.runtime_engines.base import RuntimeSession


def _minimal_scratch_project() -> dict:
    return {
        "targets": [
            {
                "isStage": True,
                "name": "Stage",
                "variables": {},
                "blocks": {
                    "hat1": {
                        "opcode": "event_whenflagclicked",
                        "next": "loop1",
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "topLevel": True,
                    },
                    "loop1": {
                        "opcode": "control_repeat",
                        "next": "bc1",
                        "parent": "hat1",
                        "inputs": {"SUBSTACK": [2, "var1"], "TIMES": [1, [4, "3"]]},
                        "fields": {},
                        "topLevel": False,
                    },
                    "var1": {
                        "opcode": "data_setvariableto",
                        "next": None,
                        "parent": "loop1",
                        "inputs": {"VALUE": [1, [4, "1"]]},
                        "fields": {"VARIABLE": ["score", "varid"]},
                        "topLevel": False,
                    },
                    "bc1": {
                        "opcode": "event_broadcast",
                        "next": None,
                        "parent": "loop1",
                        "inputs": {},
                        "fields": {"BROADCAST_OPTION": ["start", None]},
                        "topLevel": False,
                    },
                },
                "costumes": [{"name": "backdrop1", "assetId": "abc"}],
                "sounds": [],
            },
            {
                "isStage": False,
                "name": "Sprite1",
                "variables": {},
                "blocks": {
                    "hat2": {
                        "opcode": "event_whenbroadcastreceived",
                        "next": "if1",
                        "parent": None,
                        "inputs": {},
                        "fields": {"BROADCAST_OPTION": ["start", None]},
                        "topLevel": True,
                    },
                    "if1": {
                        "opcode": "control_if",
                        "next": None,
                        "parent": "hat2",
                        "inputs": {"SUBSTACK": [2, "say1"], "CONDITION": [2, "cmp1"]},
                        "fields": {},
                        "topLevel": False,
                    },
                    "cmp1": {
                        "opcode": "operator_gt",
                        "next": None,
                        "parent": "if1",
                        "inputs": {},
                        "fields": {},
                        "topLevel": False,
                    },
                    "say1": {
                        "opcode": "looks_say",
                        "next": None,
                        "parent": "if1",
                        "inputs": {"MESSAGE": [1, [4, "Hello"]]},
                        "fields": {},
                        "topLevel": False,
                    },
                },
                "costumes": [{"name": "costume1", "assetId": "def"}],
                "sounds": [],
            },
        ],
        "meta": {"semver": "3.0.0"},
    }


def _write_sb3(path: Path, project: dict | None = None) -> Path:
    project = project or _minimal_scratch_project()
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("project.json", json.dumps(project))
    return path


def test_pro_only_scratch_runtime_flag():
    assert fast_grading_flags("fast")["enable_scratch_runtime_verification"] is False
    assert deep_grading_flags("deep")["enable_scratch_runtime_verification"] is True


def test_scratch_engine_resolves(tmp_path: Path):
    sb3 = _write_sb3(tmp_path / "game.sb3")
    engine = resolve_engine(sb3)
    assert engine is not None
    assert engine.engine_id == "scratch"


def test_execution_graph_detects_loops_conditions_variables_broadcasts():
    graph = build_execution_graph(_minimal_scratch_project())
    assert graph["graph_ok"] is True
    assert graph["node_count"] >= 5
    analysis = graph["analysis"]
    assert analysis["loops"]["count"] >= 1
    assert analysis["conditions"]["count"] >= 1
    assert analysis["variables"]["count"] >= 1
    assert analysis["broadcasts"]["count"] >= 1
    assert analysis["has_control_flow"] is True
    assert analysis["has_variables"] is True
    assert analysis["has_broadcasts"] is True


def test_analyze_graph_nodes_empty():
    result = analyze_graph_nodes([])
    assert result["loops"]["count"] == 0
    assert result["has_control_flow"] is False


def test_static_graph_verification(tmp_path: Path):
    sb3 = _write_sb3(tmp_path / "demo.sb3")
    session = RuntimeSession.create(engine="scratch", submission_key="test", root=tmp_path)
    result = run_scratch_static_graph(session, sb3)
    assert result["success"] is True
    assert session.signals.get("execution_graph_ok") is True
    assert int(session.signals.get("loop_count") or 0) >= 1
