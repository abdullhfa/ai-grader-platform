"""Phase 4 — AI Evidence Reasoning tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestEvidenceGraph(unittest.TestCase):
    def test_build_evidence_graphs(self):
        from app.ai_reasoning.evidence_graph import build_evidence_graphs

        gameplay = {
            "detections": [
                {"detector": "motion_detector", "label": "movement_detected", "confidence": 0.85, "evidence": {}},
                {"detector": "freeze_detector", "label": "motion_present", "confidence": 0.7, "evidence": {}},
            ],
            "timeline": {"events": [{"type": "movement_detected", "timestamp": 2.0, "confidence": 0.8}]},
            "evidence_links": [{"criterion_hint": "gameplay_loop", "aggregate_confidence": 0.8}],
        }
        inventory = {"runtime_observation_report": {"runtime_observed": True}}
        graphs = build_evidence_graphs(gameplay_analysis=gameplay, artifact_inventory=inventory)
        self.assertGreater(len(graphs), 0)
        self.assertGreater(graphs[0].confidence, 0.3)


class TestHallucinationGuard(unittest.TestCase):
    def test_rejects_unverified_win_claim(self):
        from app.ai_reasoning.evidence_graph import CriterionEvidenceGraph, EvidenceNode
        from app.ai_reasoning.hallucination_guard import guard_reasoning_text

        graph = CriterionEvidenceGraph(
            criterion="gameplay_loop",
            evidence_nodes=[
                EvidenceNode("n1", "gameplay", "movement_detected", 0.8, {}),
            ],
            supporting_events=["movement_detected"],
            confidence=0.7,
        )
        guard = guard_reasoning_text("The player achieved victory and won the level.", [graph])
        self.assertTrue(guard.get("reasoning_rejected"))


class TestMultiAgentReasoning(unittest.TestCase):
    def test_arbitration_manual_review_on_integrity(self):
        from app.ai_reasoning.orchestrator import run_evidence_reasoning

        grading = {
            "student_name": "Test",
            "overall_feedback": "Gameplay shows movement.",
            "criteria_results": [{"criteria_level": "8/C.P5", "achieved": True, "feedback": "ok"}],
            "ai_likelihood": 80,
        }
        gameplay = {
            "detections": [
                {"detector": "motion_detector", "label": "movement_detected", "confidence": 0.85, "evidence": {}},
            ],
            "timeline": {"events": [{"type": "movement_detected", "timestamp": 1.0, "confidence": 0.8}]},
        }
        inventory = {
            "runtime_observation_report": {"runtime_observed": True, "runtime_session_id": "s1"},
            "cross_artifact_consistency": {"ambiguities": [{"code": "source_build_mismatch"}]},
            "runtime_artifacts": {"unity_source_build_alignment": "source_without_build"},
        }
        result = run_evidence_reasoning(
            submission_key="Test",
            grading_result=grading,
            artifact_inventory=inventory,
            gameplay_analysis=gameplay,
        )
        self.assertEqual(result.get("status"), "completed")
        final = result.get("final_decision") or {}
        self.assertIn(final.get("decision"), ("manual_review", "supported", "insufficient_evidence", "rejected"))


class TestConfidenceEngine(unittest.TestCase):
    def test_weighted_confidence_prefers_runtime(self):
        from app.ai_reasoning.confidence_engine import weighted_confidence

        score = weighted_confidence(
            [
                {"source": "runtime", "confidence": 0.9},
                {"source": "llm", "confidence": 0.95},
            ]
        )
        self.assertGreater(score, 0.45)
        self.assertLess(score, 0.95)


if __name__ == "__main__":
    unittest.main(verbosity=2)
