"""Tests for Godot orchestrator wiring and gameplay_verification fallback."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.gameplay_verifier import (
    _authoritative_gv_richness,
    _gameplay_verification_blob,
    resolve_authoritative_gameplay_verification,
)
from app.runtime.orchestrator import promote_nested_runtime_observations


def test_orchestrator_promotes_gameplay_verification():
    observation: dict = {"status": "completed", "runtime_observed": True}
    legacy = {
        "status": "completed",
        "runtime_observed": True,
        "gameplay_verification": {
            "gameplay_entered": False,
            "failure_reason_code": "MENU_NOT_RESOLVED",
            "failure_reason_ar": "قائمة لم تُحل",
        },
        "interaction_trace": {"visual_delta_score": 0.12, "l4_level": "L3"},
    }
    promote_nested_runtime_observations(observation, legacy, None)

    gv = observation.get("gameplay_verification") or {}
    assert gv.get("failure_reason_code") == "MENU_NOT_RESOLVED"
    assert gv.get("gameplay_entered") is False
    assert observation.get("interaction_trace", {}).get("visual_delta_score") == 0.12


def test_orchestrator_prefers_richer_godot_observation():
    observation: dict = {}
    legacy = {
        "gameplay_verification": {"gameplay_entered": None, "l4_level": "L3"},
    }
    godot = {
        "gameplay_verification": {
            "gameplay_entered": False,
            "failure_reason_code": "BOOT_TIMEOUT",
        },
    }
    promote_nested_runtime_observations(observation, legacy, godot)
    assert observation["gameplay_verification"]["failure_reason_code"] == "BOOT_TIMEOUT"


def test_gameplay_verification_blob_fallback():
    obs = {
        "runtime_observed": True,
        "signals": {
            "legacy_observation": {
                "gameplay_verification": {
                    "gameplay_entered": False,
                    "failure_reason_code": "WINDOW_NOT_FOUND",
                }
            }
        },
    }
    gv = _gameplay_verification_blob(obs, inventory={}, grading_result={"submission_id": 50})
    assert gv.get("failure_reason_code") == "WINDOW_NOT_FOUND"
    assert gv.get("gameplay_entered") is False


def test_gameplay_verification_blob_ensures_failure_code_on_partial_gv():
    obs = {
        "runtime_observed": True,
        "smoke_result": "stable_window",
        "interaction_trace": {"l4_level": "L3", "gameplay_entered": False},
        "gameplay_verification": {
            "gameplay_entered": False,
            "l4_level": "L3",
        },
    }
    gv = _gameplay_verification_blob(obs, inventory={}, grading_result={})
    assert gv.get("gameplay_entered") is False
    assert gv.get("failure_reason_code")
    assert gv.get("terminal_classify") == "consumer_ensure"


def test_build_godot_smoke_observation_promotes_gameplay_verification():
    from app.runtime_engines.godot.export_runner import build_godot_smoke_observation

    smoke = {
        "attempted": True,
        "smoke_result": "stable_window",
        "runtime_screenshots": [],
        "gameplay_verification": {
            "gameplay_entered": False,
            "failure_reason_code": "MENU_NOT_RESOLVED",
        },
        "interaction_trace": {"visual_delta_score": 0.1},
    }
    obs = build_godot_smoke_observation(smoke)
    assert obs["gameplay_verification"]["failure_reason_code"] == "MENU_NOT_RESOLVED"
    assert obs["interaction_trace"]["visual_delta_score"] == 0.1


def test_resolve_authoritative_prefers_capture_failure_over_trace_fallback():
    capture_gv = {
        "gameplay_entered": False,
        "failure_reason_code": "GAME_WINDOW_CAPTURE_FAILED",
        "terminal_classify": "capture_pipeline",
        "godot_retry_attempts": [{"step": "capture_preflight"}],
    }
    inv = {
        "runtime_observation_report": {
            "runtime_observed": True,
            "signals": {
                "legacy_observation": {
                    "artifact_analyses": [{"gameplay_verification": capture_gv}],
                }
            },
            "interaction_trace": {
                "l4_level": "L3",
                "gameplay_entered": False,
                "visual_delta_score": 0.0,
            },
        }
    }
    grading_result = {
        "gameplay_verification": {
            "gameplay_entered": False,
            "failure_reason_code": "NO_VISUAL_RESPONSE_TO_INPUT",
        }
    }
    resolved = resolve_authoritative_gameplay_verification(
        artifact_inventory=inv,
        grading_result=grading_result,
    )
    assert resolved["failure_reason_code"] == "GAME_WINDOW_CAPTURE_FAILED"
    assert _authoritative_gv_richness(capture_gv) > _authoritative_gv_richness(
        grading_result["gameplay_verification"]
    )


def test_fixture_stable_pass_and_failure_patterns():
    import scripts.godot_soak_test as soak

    pass_runs = [
        {"grade_level": "P", "gameplay_entered": True, "failure_reason_code": None},
    ] * 3
    assert soak._fixture_stable(pass_runs) is True

    fail_runs = [
        {"grade_level": "U", "gameplay_entered": False, "failure_reason_code": "PROCESS_CRASHED"},
    ] * 3
    assert soak._fixture_stable(fail_runs) is True

    mixed = pass_runs[:2] + fail_runs[:1]
    assert soak._fixture_stable(mixed) is False


def test_evaluate_matrix_requires_student_godot_2_stable():
    import scripts.godot_soak_test as soak

    sub50 = [{"grade_level": "P", "gameplay_entered": True, "failure_reason_code": None, "correct": True}] * 3
    student_ok = [{"grade_level": "P", "gameplay_entered": True, "failure_reason_code": None, "correct": True}] * 3
    student_bad = [
        {"grade_level": "P", "gameplay_entered": True, "failure_reason_code": None, "correct": True},
        {"grade_level": "U", "gameplay_entered": False, "failure_reason_code": "BOOT_TIMEOUT", "correct": True},
        {"grade_level": "P", "gameplay_entered": True, "failure_reason_code": None, "correct": True},
    ]
    runs_ok = sub50 + student_ok + student_bad[:0]
    eval_ok = soak._evaluate_matrix(
        runs_ok,
        submission_50_runs=sub50,
        student_godot_2_runs=student_ok,
        student_godot_2_pending=False,
    )
    assert eval_ok["submission_50_stable"] is True
    assert eval_ok["student_godot_2_stable"] is True
    assert eval_ok["passed"] is True

    runs_bad = sub50 + student_bad
    eval_bad = soak._evaluate_matrix(
        runs_bad,
        submission_50_runs=sub50,
        student_godot_2_runs=student_bad,
        student_godot_2_pending=False,
    )
    assert eval_bad["student_godot_2_stable"] is False
    assert eval_bad["passed"] is False


def test_soak_writes_partial_report_on_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setenv("WHATSAPP_AUTO_START", "false")

    import scripts.godot_soak_test as soak

    monkeypatch.setattr(soak, "REPORTS_DIR", reports)
    monkeypatch.setattr(soak, "FIXTURES_PATH", tmp_path / "fixtures.json")
    (tmp_path / "fixtures.json").write_text(
        json.dumps(
            {
                "fixtures": [
                    {"id": "broken", "kind": "db_submission", "submission_id": 99999},
                ],
                "runs_per_fixture": 1,
            }
        ),
        encoding="utf-8",
    )

    async def _fail_grade(*_a, **_k):
        raise RuntimeError("simulated grade failure")

    monkeypatch.setattr(soak, "_grade_submission", _fail_grade)

    out = __import__("asyncio").run(soak.run_matrix(runs_per_fixture=1))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["runs"]) == 1
    run = data["runs"][0]
    assert run["status"] == "error"
    assert "simulated grade failure" in run["error"]
    assert run.get("traceback")
