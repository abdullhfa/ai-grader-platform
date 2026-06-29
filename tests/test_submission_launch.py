"""Launch stabilization — submission validity, confidence tiers, failsafe."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestSubmissionValidity(unittest.TestCase):
    def test_missing_build_warning(self):
        from app.submission.validity_policy import assess_submission_validity

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Game.yyp").write_text(
                json.dumps({"resourceType": "GMProject", "resources": []}),
                encoding="utf-8",
            )
            (root / "objects" / "obj_a").mkdir(parents=True)
            result = assess_submission_validity(root)
            self.assertIn("missing_build", result["warnings"])
            self.assertEqual(result["validity"], "partial")

    def test_corrupted_zip(self):
        from app.submission.validity_policy import assess_submission_validity

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bad = root / "bad.zip"
            bad.write_bytes(b"not a zip")
            result = assess_submission_validity(root, paths=[str(bad)])
            self.assertTrue(result["zip_status"]["corrupted"])


class TestConfidenceTiers(unittest.TestCase):
    def test_tier_a_runtime(self):
        from app.submission.confidence_tiers import compute_confidence_tier

        tier = compute_confidence_tier(
            engine_id="unity",
            status="completed",
            runtime_method="unity_play_session_v2",
        )
        self.assertEqual(tier["tier"], "A")

    def test_tier_c_static(self):
        from app.submission.confidence_tiers import compute_confidence_tier

        tier = compute_confidence_tier(
            engine_id="gamemaker",
            status="completed",
            runtime_method="gamemaker_artifact_analysis",
        )
        self.assertEqual(tier["tier"], "C")
        self.assertTrue(tier["examiner_signoff_required"])


class TestFailsafePipeline(unittest.TestCase):
    def test_never_empty_on_skip(self):
        from app.submission.failsafe import wrap_failsafe_session_result

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "unknown.txt").write_text("data", encoding="utf-8")
            result = wrap_failsafe_session_result(
                {"status": "skipped", "reason": "no_engine_match"},
                root=root,
                submission_key="student",
            )
            self.assertTrue(result["failsafe"]["never_empty"])
            self.assertIn("confidence_tier", result)
            self.assertIn("grading_summary", result["failsafe"])

    def test_orchestrator_partial_on_gamemaker_source(self):
        from app.runtime.orchestrator import run_runtime_session

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Game.yyp").write_text(
                json.dumps({"resourceType": "GMProject", "resources": [{"a": 1}]}),
                encoding="utf-8",
            )
            (root / "objects" / "obj_x").mkdir(parents=True)
            (root / "objects" / "obj_x" / "Step_0.gml").write_text("score+=1;", encoding="utf-8")
            result = run_runtime_session("demo", root, timeout_seconds=5)
            self.assertIn("confidence_tier", result)
            self.assertIn("failsafe", result)
            self.assertTrue(result["failsafe"]["pipeline_completed"])


if __name__ == "__main__":
    unittest.main()
