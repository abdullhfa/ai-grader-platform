"""
Replay determinism tests — PHASE B2.
Run: python tests/test_replay_determinism.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestReplayDeterminism(unittest.TestCase):
    def _load_abdullah_snapshot(self):
        from app.database import SessionLocal
        from app.models import Submission

        db = SessionLocal()
        try:
            sub = db.query(Submission).filter(Submission.id == 1).first()
            if not sub or not sub.grading_snapshot_json:
                self.skipTest("submission 1 snapshot not available")
            return json.loads(str(sub.grading_snapshot_json))
        finally:
            db.close()

    def test_replay_hash_stable_ten_trials(self):
        from app.academic_event_replay import build_academic_timeline_replay
        from app.deterministic_replay_engine import verify_deterministic_replay

        snap = self._load_abdullah_snapshot()
        timeline = build_academic_timeline_replay(snap)
        events = timeline.get("events") or []
        hashes = []
        for _ in range(10):
            v = verify_deterministic_replay(events, snap)
            hashes.append(v.get("reconstructed_state_hash"))
        self.assertEqual(len(set(hashes)), 1)

    def test_protected_digest_match(self):
        from app.academic_event_replay import build_academic_timeline_replay
        from app.deterministic_replay_engine import verify_deterministic_replay

        snap = self._load_abdullah_snapshot()
        timeline = build_academic_timeline_replay(snap)
        v = verify_deterministic_replay(timeline.get("events") or [], snap)
        self.assertTrue(v.get("protected_digest_match"))
        self.assertTrue(v.get("replay_verified"))

    def test_event_replay_sorted_by_seq(self):
        from app.deterministic_replay_engine import replay_events, compute_replayed_state_hash

        snap = self._load_abdullah_snapshot()
        from app.academic_event_replay import build_academic_timeline_replay

        events = build_academic_timeline_replay(snap).get("events") or []
        if len(events) < 2:
            self.skipTest("not enough events")
        h1 = compute_replayed_state_hash(replay_events(events))
        shuffled = sorted(events, key=lambda e: int(e.get("event_seq") or 0), reverse=True)
        h2 = compute_replayed_state_hash(replay_events(shuffled))
        self.assertEqual(h1, h2)

    def test_stale_log_uses_synthetic_reconstruction(self):
        from app.academic_event_replay import build_academic_timeline_replay, persisted_event_log_stale, get_academic_event_log

        snap = self._load_abdullah_snapshot()
        persisted = list(get_academic_event_log(snap).get("events") or [])
        if not persisted:
            self.skipTest("no persisted log")
        if not persisted_event_log_stale(snap, persisted):
            self.skipTest("log not stale in this DB state")
        timeline = build_academic_timeline_replay(snap)
        self.assertEqual(timeline.get("source"), "synthetic_reconstruction_stale_log")


if __name__ == "__main__":
    unittest.main(verbosity=2)
