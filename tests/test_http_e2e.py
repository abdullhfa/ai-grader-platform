"""
HTTP end-to-end tests via FastAPI TestClient.
Run: python tests/test_http_e2e.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestHttpE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        import main

        cls.client = TestClient(main.app)

    def test_health_liveness(self):
        for path in ("/health", "/api/health"):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertIn(resp.status_code, (200, 503))
                body = resp.json()
                self.assertIn("status", body)

    def test_health_deep(self):
        resp = self.client.get("/health/deep")
        self.assertIn(resp.status_code, (200, 503))
        body = resp.json()
        self.assertIn("checks", body)

    def test_readiness(self):
        for path in ("/ready", "/api/ready"):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertIn(resp.status_code, (200, 503))
                body = resp.json()
                self.assertEqual(body.get("report_type"), "institutional_readiness")

    def test_institutional_readiness_api(self):
        resp = self.client.get("/api/institutional/readiness")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body.get("report_type"), "institutional_readiness")
        self.assertIn("checks", body)

    def test_runtime_l4_gate(self):
        resp = self.client.get("/api/runtime/l4-gate-status")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("l4_sandbox_permitted", body)

    def test_replay_cohort_registry(self):
        resp = self.client.get("/api/replay-cohort-registry")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsInstance(body, (list, dict))

    def test_governance_freeze_registry(self):
        resp = self.client.get("/api/governance/freeze-registry")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body.get("report_type"), "governance_freeze_registry")
        self.assertIn("l4_gate", body)

    def test_batch_grade_progress_not_found(self):
        resp = self.client.get("/api/batch-grade-progress/999999")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("found"), False)

    def test_batch_grade_latest(self):
        resp = self.client.get("/api/batch-grade-latest/1")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("found", body)

    def test_login_page(self):
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("content-type", ""))

    def test_governance_contracts(self):
        resp = self.client.get("/api/governance-contracts")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
