"""
PRO Scratch Verification — execution graph + scratch-vm runtime.

Pipeline:
  1. Load project.json from .sb3
  2. Graph Builder — blocks → execution graph (loops/conditions/variables/broadcasts)
  3. Scratch VM — green flag, record variables, events, outputs
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from app.runtime_engines.base import RuntimeSession, SessionStatus
from app.runtime_engines.scratch.graph_builder import build_execution_graph
from app.runtime_engines.scratch.project_probe import find_scratch_project, load_scratch_project_json
from app.runtime_engines.scratch.scratch_vm_runner import run_scratch_vm

logger = logging.getLogger("ai_grader.runtime.scratch.verification")


def run_scratch_runtime_verification(
    session: RuntimeSession,
    sb3_path: Path,
    *,
    timeout_seconds: int = 25,
) -> Dict[str, Any]:
    """Full PRO verification: graph analysis + optional VM execution."""
    loaded = load_scratch_project_json(sb3_path)
    if not loaded.get("ok"):
        session.status = SessionStatus.FAILED
        session.errors.append(str(loaded.get("error")))
        return {"success": False, "error": loaded.get("error")}

    project = loaded["project"]
    graph = build_execution_graph(project)
    analysis = graph.get("analysis") or {}

    vm_result = run_scratch_vm(
        sb3_path,
        timeout_seconds=min(timeout_seconds, 45),
        max_steps=1200,
    )

    graph_ok = bool(graph.get("graph_ok"))
    vm_ran = bool(vm_result.get("success") or vm_result.get("ran"))
    has_control = bool(analysis.get("has_control_flow"))
    has_vars = bool(analysis.get("has_variables"))
    has_broadcasts = bool(analysis.get("has_broadcasts"))

    signals = {
        "execution_graph_ok": graph_ok,
        "graph_node_count": int(graph.get("node_count") or 0),
        "loop_count": int((analysis.get("loops") or {}).get("count") or 0),
        "condition_count": int((analysis.get("conditions") or {}).get("count") or 0),
        "variable_block_count": int((analysis.get("variables") or {}).get("count") or 0),
        "broadcast_count": int((analysis.get("broadcasts") or {}).get("count") or 0),
        "has_control_flow": has_control,
        "has_variables": has_vars,
        "has_broadcasts": has_broadcasts,
        "scratch_vm_ran": vm_ran,
        "scratch_vm_method": vm_result.get("method"),
        "scratch_stage_snapshot": vm_result.get("stage_snapshot"),
        "variable_snapshots": len(vm_result.get("variables") or []),
        "broadcast_events": len(vm_result.get("broadcasts") or []),
        "output_events": len(vm_result.get("outputs") or []),
        "runtime_events": len(vm_result.get("events") or []),
        "functional_smoke_pass": graph_ok and (vm_ran or vm_result.get("method") == "static_graph_only"),
    }

    result = {
        "success": signals["functional_smoke_pass"],
        "method": "scratch_pro_runtime_verification",
        "execution_graph": graph,
        "scratch_vm": vm_result,
        "signals": signals,
        "scratch_runtime_verification": {
            "version": "scratch_runtime_verification_v1",
            "sb3": str(sb3_path),
            "format": loaded.get("format"),
        },
    }

    session.signals.update(signals)
    session.signals["execution_graph"] = graph
    session.signals["scratch_vm"] = vm_result
    session.signals["scratch_runtime_verification"] = result["scratch_runtime_verification"]
    session.signals["runtime_method"] = result["method"]

    if graph_ok:
        session.status = SessionStatus.COMPLETED
        if not vm_ran and vm_result.get("method") != "static_graph_only":
            session.signals["runtime_partial"] = True
    else:
        session.status = SessionStatus.FAILED

    session.events.record(
        "scratch_pro_runtime_verification",
        nodes=signals["graph_node_count"],
        loops=signals["loop_count"],
        vm_ran=vm_ran,
    )
    return result


def run_scratch_static_graph(session: RuntimeSession, sb3_path: Path) -> Dict[str, Any]:
    """BASIC — graph from JSON only (no VM)."""
    loaded = load_scratch_project_json(sb3_path)
    if not loaded.get("ok"):
        session.status = SessionStatus.FAILED
        return {"success": False, "error": loaded.get("error")}

    graph = build_execution_graph(loaded["project"])
    analysis = graph.get("analysis") or {}
    session.signals["execution_graph"] = graph
    session.signals["runtime_method"] = "scratch_static_graph"
    session.signals["execution_graph_ok"] = bool(graph.get("graph_ok"))
    session.signals["loop_count"] = int((analysis.get("loops") or {}).get("count") or 0)
    session.status = SessionStatus.COMPLETED
    session.events.record("scratch_static_graph", nodes=int(graph.get("node_count") or 0))
    return {"success": bool(graph.get("graph_ok")), "execution_graph": graph, "method": "scratch_static_graph"}
