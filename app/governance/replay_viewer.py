"""Replay-first inspection bundle for examiner review."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ReplayInspectionBundle:
    """
    Canonical replay package for institutional review.

    uploads/replay_snapshots/{submission_key}/{session_id}/
        runtime/runtime.json
        timeline/timeline.json  (or gameplay)
        evidence/evidence.json
        ai_reasoning/ai_reasoning.json
        screenshots/
        deterministic_hash.json
    """

    submission_key: str
    session_id: str
    snapshot_root: str
    deterministic_hash: Optional[str] = None
    runtime: Dict[str, Any] = field(default_factory=dict)
    timeline: Dict[str, Any] = field(default_factory=dict)
    evidence: Any = None
    ai_reasoning: Dict[str, Any] = field(default_factory=dict)
    grading_summary: Dict[str, Any] = field(default_factory=dict)
    screenshots: List[str] = field(default_factory=list)
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    confidence_scores: Dict[str, Any] = field(default_factory=dict)
    hallucination_flags: List[Any] = field(default_factory=list)
    bundle_complete: bool = False
    missing_sections: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "submission_key": self.submission_key,
            "session_id": self.session_id,
            "snapshot_root": self.snapshot_root,
            "deterministic_hash": self.deterministic_hash,
            "runtime": self.runtime,
            "timeline": self.timeline,
            "evidence": self.evidence,
            "ai_reasoning": self.ai_reasoning,
            "grading_summary": self.grading_summary,
            "screenshots": self.screenshots,
            "contradictions": self.contradictions,
            "confidence_scores": self.confidence_scores,
            "hallucination_flags": self.hallucination_flags,
            "bundle_complete": self.bundle_complete,
            "missing_sections": self.missing_sections,
            "review_mode": "replay_first",
        }


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _snapshot_base(submission_key: str, session_id: str) -> Path:
    return Path("uploads/replay_snapshots") / submission_key / session_id


def load_replay_inspection_bundle(
    submission_key: str,
    session_id: str,
) -> ReplayInspectionBundle:
    """Load replay snapshot — examiner sees evidence, not LLM summary alone."""
    base = _snapshot_base(submission_key, session_id)
    bundle = ReplayInspectionBundle(
        submission_key=submission_key,
        session_id=session_id,
        snapshot_root=str(base),
    )

    if not base.is_dir():
        bundle.missing_sections.append("snapshot_root")
        return bundle

    hash_doc = _read_json(base / "deterministic_hash.json")
    if isinstance(hash_doc, dict):
        bundle.deterministic_hash = hash_doc.get("deterministic_hash")

    bundle.runtime = _read_json(base / "runtime" / "runtime.json") or {}
    bundle.timeline = (
        _read_json(base / "timeline" / "timeline.json")
        or _read_json(base / "gameplay" / "gameplay.json")
        or {}
    )
    bundle.evidence = _read_json(base / "evidence" / "evidence.json")
    bundle.ai_reasoning = _read_json(base / "ai_reasoning" / "ai_reasoning.json") or {}
    bundle.grading_summary = _read_json(base / "grading_summary" / "grading_summary.json") or {}

    shots_dir = base / "screenshots"
    if shots_dir.is_dir():
        bundle.screenshots = sorted(str(p) for p in shots_dir.glob("*") if p.is_file())

    # Extract governance signals from ai_reasoning (not LLM prose)
    final = bundle.ai_reasoning.get("final_decision") or {}
    bundle.confidence_scores = {
        "graph_confidence": final.get("confidence"),
        "decision": final.get("decision"),
        "requires_manual_review": final.get("requires_manual_review"),
    }
    bundle.hallucination_flags = list(bundle.ai_reasoning.get("hallucination_flags") or [])
    guard = bundle.ai_reasoning.get("hallucination_guard") or {}
    if guard.get("flags"):
        bundle.hallucination_flags.extend(guard.get("flags") or [])

    for opinion in bundle.ai_reasoning.get("agent_opinions") or []:
        if isinstance(opinion, dict) and opinion.get("contradictions"):
            bundle.contradictions.extend(opinion["contradictions"])

    required = ["runtime", "evidence", "ai_reasoning", "deterministic_hash"]
    for section in required:
        if section == "deterministic_hash":
            if not bundle.deterministic_hash:
                bundle.missing_sections.append(section)
        elif section == "runtime" and not bundle.runtime:
            bundle.missing_sections.append(section)
        elif section == "evidence" and bundle.evidence is None:
            bundle.missing_sections.append(section)
        elif section == "ai_reasoning" and not bundle.ai_reasoning:
            bundle.missing_sections.append(section)

    bundle.bundle_complete = len(bundle.missing_sections) == 0
    return bundle


def find_sessions_for_submission(submission_key: str) -> List[str]:
    root = Path("uploads/replay_snapshots") / submission_key
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir())
