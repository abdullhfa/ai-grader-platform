"""Weighted confidence arbitration — LLM is lowest-trust source."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

SOURCE_WEIGHTS: Dict[str, float] = {
    "runtime": 0.95,
    "telemetry": 0.90,
    "log": 0.88,
    "timeline": 0.82,
    "gameplay": 0.75,
    "ocr": 0.75,
    "cv": 0.65,
    "static": 0.60,
    "llm": 0.45,
    "unknown": 0.40,
}


def weighted_confidence(
    items: List[Dict[str, Any]],
    *,
    source_key: str = "source",
    confidence_key: str = "confidence",
) -> float:
    if not items:
        return 0.0
    total_w = 0.0
    total = 0.0
    for item in items:
        if not isinstance(item, dict):
            continue
        source = str(item.get(source_key) or "unknown")
        conf = float(item.get(confidence_key) or 0.0)
        weight = SOURCE_WEIGHTS.get(source, SOURCE_WEIGHTS["unknown"])
        total_w += weight
        total += conf * weight
    if total_w <= 0:
        return 0.0
    return round(total / total_w, 3)


def arbitrate_confidence(
    graph_confidence: float,
    agent_confidences: List[float],
    *,
    llm_confidence: Optional[float] = None,
) -> float:
    parts = [{"source": "gameplay", "confidence": graph_confidence}]
    for conf in agent_confidences:
        parts.append({"source": "gameplay", "confidence": conf})
    if llm_confidence is not None:
        parts.append({"source": "llm", "confidence": llm_confidence})
    return weighted_confidence(parts)
