"""Tests for admin replay-cache invalidation."""
from __future__ import annotations

from types import SimpleNamespace

from app.submission_replay_cache import (
    bump_replay_cache_generation,
    current_replay_cache_generation,
    submission_replay_cache_valid,
)


def test_bump_invalidates_legacy_submissions():
    start = current_replay_cache_generation()
    legacy = SimpleNamespace(grading_snapshot_json=None)
    assert submission_replay_cache_valid(legacy) is True

    bump_replay_cache_generation()
    assert current_replay_cache_generation() == start + 1
    assert submission_replay_cache_valid(legacy) is False
