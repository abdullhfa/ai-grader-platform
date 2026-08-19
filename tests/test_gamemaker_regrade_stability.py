"""Replay-stability contract for GameMaker submissions."""

from app.archive_extraction_utils import build_grading_fingerprint, hash_submission_file
from app.strict_grading_policy import skip_grading_cache_default


def test_identical_gamemaker_submission_keeps_one_replay_key(tmp_path, monkeypatch):
    monkeypatch.delenv("AI_GRADER_FORCE_REGRADE", raising=False)
    monkeypatch.delenv("AI_GRADER_SKIP_GRADING_CACHE", raising=False)
    submission = tmp_path / "student_game.zip"
    submission.write_bytes(b"gamemaker-project-v1-same-student-content")
    source_hash = hash_submission_file(str(submission))
    inputs = dict(source_hash=source_hash, reference_solution={"unit": "BTEC IT"}, grading_criteria=[{"criteria_level": "P1"}, {"criteria_level": "M1"}], selected_criteria=["P1", "M1"], model_version="gamemaker-runtime-v1", prompt_version="stable-gameplay-contract-v1")
    assert build_grading_fingerprint(**inputs) == build_grading_fingerprint(**inputs)
    assert skip_grading_cache_default() is False


def test_explicit_regrade_can_bypass_gamemaker_replay_cache(monkeypatch):
    monkeypatch.setenv("AI_GRADER_FORCE_REGRADE", "true")
    assert skip_grading_cache_default() is True
