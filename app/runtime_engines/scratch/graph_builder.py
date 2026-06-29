"""
Scratch Execution Graph Builder — beyond raw JSON.

Walks block chains into an execution graph and analyzes:
  loops, conditions, variables, broadcast events.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

_LOOP_OPCODES = frozenset(
    {
        "control_repeat",
        "control_forever",
        "control_repeat_until",
        "control_while",
        "control_for_each",
    }
)
_CONDITION_OPCODES = frozenset(
    {
        "control_if",
        "control_if_else",
        "control_wait_until",
    }
)
_VARIABLE_OPCODES = frozenset(
    {
        "data_setvariableto",
        "data_changevariableby",
        "data_showvariable",
        "data_hidevariable",
        "data_addtolist",
        "data_deleteoflist",
        "data_deletealloflist",
        "data_insertatlist",
        "data_replaceitemoflist",
        "data_itemoflist",
        "data_listcontainsitem",
    }
)
_BROADCAST_OPCODES = frozenset(
    {
        "event_broadcast",
        "event_broadcastandwait",
        "event_whenbroadcastreceived",
    }
)
_HAT_PREFIX = "event_"


def _input_block_id(value: Any) -> Optional[str]:
    if isinstance(value, list) and len(value) >= 2:
        if value[0] in (1, 2, 3) and isinstance(value[1], str):
            return value[1]
    return None


def _collect_substack(blocks: Dict[str, Any], block_id: str, slot: str) -> List[str]:
    block = blocks.get(block_id) or {}
    inputs = block.get("inputs") or {}
    sub = inputs.get(slot)
    sub_id = _input_block_id(sub)
    if not sub_id:
        return []
    return _walk_chain(blocks, sub_id)


def _walk_chain(blocks: Dict[str, Any], start_id: str) -> List[str]:
    chain: List[str] = []
    current: Optional[str] = start_id
    seen: Set[str] = set()
    while current and current not in seen:
        seen.add(current)
        chain.append(current)
        block = blocks.get(current) or {}
        for slot in ("SUBSTACK", "SUBSTACK2"):
            chain.extend(_collect_substack(blocks, current, slot))
        current = block.get("next")
    return chain


def _find_hat_blocks(blocks: Dict[str, Any]) -> List[str]:
    hats: List[str] = []
    for bid, block in blocks.items():
        if not isinstance(block, dict):
            continue
        opcode = str(block.get("opcode") or "")
        if opcode.startswith(_HAT_PREFIX) or block.get("topLevel"):
            if opcode.startswith(_HAT_PREFIX) or opcode in ("procedures_definition",):
                hats.append(bid)
    return hats


def build_execution_graph(project: Dict[str, Any]) -> Dict[str, Any]:
    """Build execution graph nodes/edges per target (sprite/stage)."""
    targets = project.get("targets") or []
    graphs: List[Dict[str, Any]] = []
    all_nodes: List[Dict[str, Any]] = []
    all_edges: List[Dict[str, Any]] = []

    for target in targets:
        if not isinstance(target, dict):
            continue
        tname = str(target.get("name") or "?")
        blocks: Dict[str, Any] = target.get("blocks") or {}
        if not isinstance(blocks, dict):
            continue

        hats = _find_hat_blocks(blocks)
        chains: List[Dict[str, Any]] = []
        for hat_id in hats:
            chain_ids = _walk_chain(blocks, hat_id)
            nodes = []
            for bid in chain_ids:
                b = blocks.get(bid) or {}
                opcode = str(b.get("opcode") or "")
                nodes.append(
                    {
                        "id": bid,
                        "opcode": opcode,
                        "target": tname,
                        "fields": b.get("fields") or {},
                    }
                )
                if b.get("next"):
                    all_edges.append({"from": bid, "to": b["next"], "type": "next", "target": tname})
                for slot in ("SUBSTACK", "SUBSTACK2"):
                    sub_id = _input_block_id((b.get("inputs") or {}).get(slot))
                    if sub_id:
                        all_edges.append({"from": bid, "to": sub_id, "type": slot.lower(), "target": tname})
            chains.append({"hat_id": hat_id, "node_ids": chain_ids, "length": len(chain_ids)})
            all_nodes.extend(nodes)

        graphs.append({"target": tname, "is_stage": bool(target.get("isStage")), "hat_count": len(hats), "chains": chains})

    analysis = analyze_graph_nodes(all_nodes)
    return {
        "version": "scratch_execution_graph_v1",
        "target_graphs": graphs,
        "nodes": all_nodes,
        "edges": all_edges,
        "analysis": analysis,
        "node_count": len(all_nodes),
        "edge_count": len(all_edges),
        "graph_ok": len(all_nodes) > 0,
    }


def analyze_graph_nodes(nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    loops: List[Dict[str, Any]] = []
    conditions: List[Dict[str, Any]] = []
    variables: List[Dict[str, Any]] = []
    broadcasts: List[Dict[str, Any]] = []

    for node in nodes:
        opcode = str(node.get("opcode") or "")
        entry = {"opcode": opcode, "target": node.get("target"), "id": node.get("id")}
        fields = node.get("fields") or {}
        if opcode in _LOOP_OPCODES:
            loops.append(entry)
        if opcode in _CONDITION_OPCODES or opcode.startswith("operator_"):
            if opcode.startswith("operator_") and opcode not in (
                "operator_equals",
                "operator_lt",
                "operator_gt",
                "operator_and",
                "operator_or",
                "operator_not",
            ):
                pass
            else:
                if opcode in _CONDITION_OPCODES or opcode.startswith("operator_"):
                    conditions.append(entry)
        if opcode in _VARIABLE_OPCODES:
            var_name = ""
            if "VARIABLE" in fields:
                var_name = fields["VARIABLE"][0] if isinstance(fields["VARIABLE"], list) else str(fields["VARIABLE"])
            elif "LIST" in fields:
                var_name = fields["LIST"][0] if isinstance(fields["LIST"], list) else str(fields["LIST"])
            entry["variable"] = var_name
            variables.append(entry)
        if opcode in _BROADCAST_OPCODES:
            msg = ""
            if "BROADCAST_OPTION" in fields:
                msg = fields["BROADCAST_OPTION"][0] if isinstance(fields["BROADCAST_OPTION"], list) else ""
            entry["message"] = msg
            broadcasts.append(entry)

    return {
        "loops": {"count": len(loops), "items": loops[:20]},
        "conditions": {"count": len(conditions), "items": conditions[:20]},
        "variables": {"count": len(variables), "items": variables[:20]},
        "broadcasts": {"count": len(broadcasts), "items": broadcasts[:20]},
        "has_control_flow": len(loops) > 0 or len(conditions) > 0,
        "has_variables": len(variables) > 0,
        "has_broadcasts": len(broadcasts) > 0,
    }
