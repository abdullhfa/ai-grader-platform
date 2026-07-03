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
