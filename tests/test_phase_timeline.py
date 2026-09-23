"""Tests for the per-phase grading stopwatch (slow-run diagnosis, 2026-07-07).

Motivation: a single-student PRO run took 70+ minutes with no visibility into
where time went (67 min pre-runtime, then 'saving' for 50+ min). The timeline
makes every phase's duration explicit in batch progress.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.batch_grade_worker import advance_phase_timeline, close_phase_timeline  # noqa: E402


class TestPhaseTimeline:
    def test_records_phases_with_durations(self):
        info: dict = {}
        advance_phase_timeline(info, "extracting", now=100.0)
        advance_phase_timeline(info, "vision", now=160.0)
        advance_phase_timeline(info, "grading", now=460.0)
        close_phase_timeline(info, now=520.0)
        tl = info["phase_timeline"]
        assert [e["phase"] for e in tl] == ["extracting", "vision", "grading"]
        assert tl[0]["duration_s"] == 60.0
        assert tl[1]["duration_s"] == 300.0
        assert tl[2]["duration_s"] == 60.0
        assert all("label" in e and "started_at" in e for e in tl)

    def test_repeated_same_phase_not_duplicated(self):
        info: dict = {}
        advance_phase_timeline(info, "grading", now=10.0)
        advance_phase_timeline(info, "grading", now=20.0)
        advance_phase_timeline(info, "grading", now=30.0)
        assert len(info["phase_timeline"]) == 1

    def test_close_is_idempotent_and_safe_on_empty(self):
        info: dict = {}
        close_phase_timeline(info, now=5.0)  # no crash on empty
        advance_phase_timeline(info, "saving", now=10.0)
        close_phase_timeline(info, now=70.0)
        close_phase_timeline(info, now=99.0)  # second close must not overwrite
        assert info["phase_timeline"][-1]["duration_s"] == 60.0

    def test_arabic_labels_attached(self):
        info: dict = {}
        advance_phase_timeline(info, "saving", now=1.0)
        assert info["phase_timeline"][0]["label"] == "حفظ النتائج..."
