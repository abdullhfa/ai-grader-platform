"""Evidence graph — LLM may reason only over registered nodes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EvidenceNode:
    node_id: str
    source: str  # runtime | gameplay | ocr | telemetry | timeline | log | static
    label: str
    confidence: float
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "source": self.source,
            "label": self.label,
            "confidence": self.confidence,
            "payload": self.payload,
        }


@dataclass
class CriterionEvidenceGraph:
    criterion: str
    criterion_level: str = ""
    evidence_nodes: List[EvidenceNode] = field(default_factory=list)
    supporting_events: List[str] = field(default_factory=list)
    contradicting_events: List[str] = field(default_factory=list)
    confidence: float = 0.0
    corroboration_strength: str = "weak"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "criterion": self.criterion,
            "criterion_level": self.criterion_level,
            "evidence_nodes": [n.to_dict() for n in self.evidence_nodes],
            "supporting_events": self.supporting_events,
            "contradicting_events": self.contradicting_events,
            "confidence": self.confidence,
            "corroboration_strength": self.corroboration_strength,
            "node_count": len(self.evidence_nodes),
        }


CRITERION_EVIDENCE_REQUIREMENTS: Dict[str, Dict[str, Any]] = {
    "game_launch": {
        "required_any": ["motion_detected", "menu_ui_detected", "scene_loaded", "runtime_observed"],
        "contradicts": ["freeze_detected", "crash_detected"],
    },
    "gameplay_loop": {
        "required_any": ["movement_detected", "progression_detected", "score_hud_detected"],
        "contradicts": ["freeze_detected"],
    },
    "win_lose_state": {
        "required_any": ["win_detected", "lose_detected"],
        "contradicts": [],
    },
    "lose_health": {
        "required_any": ["death_detected", "score_hud_detected"],
        "contradicts": [],
    },
    "testing_evidence": {
        "required_any": ["input_simulated", "fps_ok", "testing_documentation"],
        "contradicts": [],
    },
    "C.P5": {
        "required_any": ["runtime_observed", "movement_detected", "manual_playtest"],
        "contradicts": ["freeze_detected", "crash_detected"],
    },
    "C.P6": {
        "required_any": ["testing_documentation", "input_simulated", "manual_playtest"],
        "contradicts": [],
    },
}


def _add_node(
    nodes: List[EvidenceNode],
    node_id: str,
    source: str,
    label: str,
    confidence: float,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    if any(n.node_id == node_id for n in nodes):
        return
    nodes.append(
        EvidenceNode(
            node_id=node_id,
            source=source,
            label=label,
            confidence=confidence,
            payload=payload or {},
        )
    )


def build_evidence_graphs(
    *,
    gameplay_analysis: Optional[Dict[str, Any]] = None,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    grading_criteria: Optional[List[Dict[str, Any]]] = None,
) -> List[CriterionEvidenceGraph]:
    gameplay = gameplay_analysis or {}
    inventory = artifact_inventory or {}
    graphs: List[CriterionEvidenceGraph] = []

    # Collect global evidence nodes from gameplay pipeline
    global_nodes: List[EvidenceNode] = []
    detections = gameplay.get("detections") or []
    for det in detections:
        if not isinstance(det, dict):
            continue
        _add_node(
            global_nodes,
            f"det:{det.get('detector')}:{det.get('label')}",
            "gameplay",
            str(det.get("label") or ""),
            float(det.get("confidence") or 0.5),
            det.get("evidence") or {},
        )

    timeline = gameplay.get("timeline") or {}
    for event in timeline.get("events") or []:
        if not isinstance(event, dict):
            continue
        _add_node(
            global_nodes,
            f"evt:{event.get('type')}:{event.get('timestamp')}",
            "timeline",
            str(event.get("type") or ""),
            float(event.get("confidence") or 0.6),
            event.get("payload") or {},
        )

    obs = inventory.get("runtime_observation_report") or {}
    if obs.get("runtime_observed"):
        _add_node(global_nodes, "runtime:observed", "runtime", "runtime_observed", 0.9, {})
    if obs.get("crash_detected"):
        _add_node(global_nodes, "runtime:crash", "runtime", "crash_detected", 0.92, {})
    metrics = obs.get("runtime_metrics") or gameplay.get("telemetry") or {}
    if metrics.get("freeze_detected"):
        _add_node(global_nodes, "telemetry:freeze", "telemetry", "freeze_detected", 0.85, metrics)

    evidence_links = gameplay.get("evidence_links") or []
    hint_to_nodes: Dict[str, List[EvidenceNode]] = {}
    for link in evidence_links:
        hint = str(link.get("criterion_hint") or "")
        hint_to_nodes[hint] = list(global_nodes)

    # Map BTEC criteria levels from grading criteria list
    criteria_levels = []
    for cr in grading_criteria or []:
        if isinstance(cr, dict):
            lv = str(cr.get("criteria_level") or cr.get("level") or "")
            if lv:
                criteria_levels.append(lv)

    targets = set(CRITERION_EVIDENCE_REQUIREMENTS.keys())
    for lv in criteria_levels:
        key = lv.split(".")[-1] if "." in lv else lv
        targets.add(key)
        targets.add(lv)

    for criterion in sorted(targets):
        req = CRITERION_EVIDENCE_REQUIREMENTS.get(criterion, {})
        nodes = list(hint_to_nodes.get(criterion, global_nodes))
        supporting = [n.label for n in nodes if n.label in (req.get("required_any") or [])]
        contradicting = [n.label for n in nodes if n.label in (req.get("contradicts") or [])]

        if not supporting and nodes:
            supporting = [n.label for n in nodes[:4]]

        confidences = [n.confidence for n in nodes if n.label in supporting]
        confidence = sum(confidences) / len(confidences) if confidences else 0.35
        if contradicting:
            confidence = max(0.1, confidence - 0.25)

        strength = (
            "strong" if confidence >= 0.75 and len(supporting) >= 2 else
            "moderate" if confidence >= 0.55 else "weak"
        )
        graphs.append(
            CriterionEvidenceGraph(
                criterion=criterion,
                criterion_level=criterion if "." in criterion else "",
                evidence_nodes=nodes,
                supporting_events=supporting,
                contradicting_events=contradicting,
                confidence=round(confidence, 3),
                corroboration_strength=strength,
            )
        )

    return graphs
