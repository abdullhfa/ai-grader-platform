"""
Production integration test suite — unittest (no pytest required).
Run: python tests/test_production_suite.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestProductionConfig(unittest.TestCase):
    def test_config_loads(self):
        from app.core.production_config import get_production_config

        cfg = get_production_config()
        self.assertGreater(cfg.sandbox_timeout_seconds, 0)
        self.assertTrue(cfg.enable_deterministic_rubric)


class TestRuntimeValidation(unittest.TestCase):
    def test_freeze_detection(self):
        from app.runtime.validation_engine import detect_freeze, validate_runtime_observation

        obs = {
            "status": "completed",
            "runtime_duration_seconds": 10,
            "runtime_signal_graph": {"signals": {"visual_response_to_input": "none"}},
        }
        freeze = detect_freeze(obs)
        self.assertTrue(freeze["freeze_suspected"])
        report = validate_runtime_observation(obs)
        self.assertIn("functional_smoke", report)

    def test_crash_detection(self):
        from app.runtime.validation_engine import detect_crash

        self.assertTrue(detect_crash({"crash_detected": True})["crash_detected"])


class TestDeterministicRubric(unittest.TestCase):
    def test_missing_evidence_blocks(self):
        from app.rubric.deterministic_engine import evaluate_criterion_deterministic

        row = evaluate_criterion_deterministic(
            criteria_level="8/B.P3",
            criteria_description="GDD document",
            student_text="short",
            evidence_gate_row={"missing_artifacts": ["gdd_document"]},
        )
        self.assertFalse(row["deterministic_achieved"])

    def test_arabic_produce_in_design_criteria_not_routed_to_p5_code_path(self):
        from app.rubric.deterministic_engine import evaluate_criterion_deterministic

        desc = "إنتاج تصميمات فنية أساسية لألعاب الحاسوب."
        long_gdd = "تصميم لعبة " + ("محتوى GDD " * 120)
        row = evaluate_criterion_deterministic(
            criteria_level="B.P3",
            criteria_description=desc,
            student_text=long_gdd,
        )
        self.assertEqual(row["rule_id"], "gdd_document")
        self.assertNotEqual(row["reason"], "no_code_evidence")


class TestAIReliability(unittest.TestCase):
    def test_high_risk_with_gaps(self):
        from app.ai.reliability_layer import score_ai_confidence

        conf = score_ai_confidence(
            {"ai_likelihood": 80, "criteria_results": [{"achieved": True}] * 4},
            evidence_gate={"has_gaps": True},
        )
        self.assertIn(conf["hallucination_risk"], ("medium", "high"))


class TestSandboxEngine(unittest.TestCase):
    def test_python_syntax_check(self):
        from app.runtime.sandbox_engine import _validate_python_script

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "ok.py"
            p.write_text("x = 1\n", encoding="utf-8")
            result = _validate_python_script(p, 5)
            self.assertEqual(result["status"], "completed")

    def test_platform_detect(self):
        from app.runtime.sandbox_engine import detect_platform

        self.assertEqual(detect_platform(Path("game.apk")), "apk")
        self.assertEqual(detect_platform(Path("main.py")), "python")


class TestGradingPipeline(unittest.TestCase):
    def test_prepare_expands_paths(self):
        from app.core.grading_pipeline import _prepare_student_files

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "student"
            root.mkdir()
            (root / "game.exe").write_bytes(b"x")
            assets = root / "Assets"
            assets.mkdir()
            cs = assets / "A.cs"
            cs.write_text("class A {}", encoding="utf-8")
            prepared = _prepare_student_files(
                [{"name": "student", "path": str(cs), "submission_paths": [str(cs)]}]
            )
            paths = prepared[0]["submission_paths"]
            self.assertTrue(any("game.exe" in p for p in paths))


class TestInstitutionalReadiness(unittest.TestCase):
    def test_report_without_db(self):
        from app.institutional.readiness_report import build_institutional_readiness_report

        report = build_institutional_readiness_report(None)
        self.assertEqual(report["report_type"], "institutional_readiness")
        self.assertIn("checks", report)


class TestHealthEndpoint(unittest.TestCase):
    def test_health_status(self):
        from app.production.hardening import build_health_status

        status = build_health_status(True)
        self.assertEqual(status["status"], "ok")
        self.assertIn("l4_gate", status)


class TestEvidenceGateIntegration(unittest.TestCase):
    def test_gate_module(self):
        import test_completion_layers as tcl

        tcl.test_evidence_gate_flags_missing_gdd(Path(tempfile.mkdtemp()))
        tcl.test_l4_permitted_with_epoch2_state()


if __name__ == "__main__":
    unittest.main(verbosity=2)
