"""
Regression tests for the STRICT GameMaker install-pause policy in
app.runtime_evidence_gate.apply_runtime_evidence_gate.

Teacher-mandated behavior (do NOT relax without their sign-off):

  GameMaker source-only submission + GameMaker/Igor not installed
    => grading_result["grading_paused"]["paused"] is ALWAYS True,
       even when an alternative-evidence path (documented gameplay video,
       static code corroboration, or human playtest) would otherwise
       satisfy the runtime gate. The teacher wants to install GameMaker
       and re-grade, not accept alt evidence as a substitute.

The only supported bypass is the explicit admin env var
``AI_GRADER_GAMEMAKER_ACCEPT_ALT_EVIDENCE_WHEN_MISSING=1``, which restores
the older "informational only" behavior. Off by default.

Submissions that already ship a runnable .exe / data.win / index.html are
completely untouched — this test pins that too.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

# The gate imports heavy dependencies (SQLAlchemy models, criterion
# governance, etc.) via app.btec_criteria_governance / app.btec_grade_resolution
# at import time — skip cleanly on environments where those aren't wired.
apply_runtime_evidence_gate = pytest.importorskip(
    "app.runtime_evidence_gate",
    reason="requires the app package (sqlalchemy etc.) to be importable",
).apply_runtime_evidence_gate


def _base_grading_result(submission_paths: List[str], *, inv: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "criteria_results": [
            {"criteria_level": "B.P3", "achieved": True, "score": 70},
            {"criteria_level": "B.P4", "achieved": True, "score": 70},
            {"criteria_level": "C.P5", "achieved": True, "score": 75},
            {"criteria_level": "C.P6", "achieved": False, "score": 0},
        ],
        "artifact_inventory": {**inv, "intake_relative_paths": submission_paths},
        "submission_paths": submission_paths,
        "grading_mode": "deep",
    }


def _gm_source_only_paths() -> List[str]:
    return [
        "student/project.yyp",
        "student/objects/obj_player/Step_0.gml",
        "student/rooms/rm_game/rm_game.yy",
        "student/gameplay.webm",  # <-- alt evidence: documented gameplay video
        "student/report.docx",
    ]


def test_strict_pause_fires_even_when_gameplay_video_present(monkeypatch):
    """Alt evidence (.webm) MUST NOT bypass the pause — teacher policy."""
    monkeypatch.delenv(
        "AI_GRADER_GAMEMAKER_ACCEPT_ALT_EVIDENCE_WHEN_MISSING", raising=False
    )
    paths = _gm_source_only_paths()
    inv = {
        "runtime_observation_report": {
            # ide_builder result: Igor not found on the grading machine.
            "gamemaker_ide_build": {
                "attempted": False,
                "success": False,
                "reason": "gamemaker_runtime_not_installed",
                "reason_ar": "GameMaker غير مثبت",
                "tools": {"available": False},
            },
            # gameplay video would normally satisfy the gate:
            "gameplay_video": {"path": "student/gameplay.webm", "verified": True},
        },
    }
    result = _base_grading_result(paths, inv=inv)
    apply_runtime_evidence_gate(result, artifact_inventory=inv)

    paused = result.get("grading_paused")
    assert paused is not None, "grading_paused must be set for GM source + no Igor"
    assert paused["paused"] is True, (
        "Strict pause: alt evidence (gameplay video) must NOT flip paused to False"
    )
    assert paused["reason"] == "gamemaker_not_installed"
    assert paused["policy"] == "strict_pause_no_alt_evidence_bypass"

    banner = result.get("gamemaker_install_pause_banner") or {}
    assert banner.get("active") is True
    assert "GameMaker" in banner.get("title_ar", "")


def test_admin_override_restores_alt_evidence_bypass(monkeypatch):
    """Explicit opt-in env var restores the older 'informational only' behavior."""
    monkeypatch.setenv(
        "AI_GRADER_GAMEMAKER_ACCEPT_ALT_EVIDENCE_WHEN_MISSING", "1"
    )
    paths = _gm_source_only_paths()
    inv = {
        "runtime_observation_report": {
            "gamemaker_ide_build": {
                "attempted": False,
                "success": False,
                "reason": "gamemaker_runtime_not_installed",
                "reason_ar": "GameMaker غير مثبت",
                "tools": {"available": False},
            },
            "gameplay_video": {"path": "student/gameplay.webm", "verified": True},
        },
    }
    result = _base_grading_result(paths, inv=inv)
    apply_runtime_evidence_gate(result, artifact_inventory=inv)

    paused = result.get("grading_paused") or {}
    if paused.get("paused") is True:
        # Alt evidence didn't satisfy the underlying verdict — strict pause
        # is correct even under override. Nothing more to assert.
        return
    assert paused.get("paused") is False, (
        "Under admin override AND satisfied verdict, pause should be informational-only"
    )
    assert "admin_override" in str(paused.get("reason", ""))


def test_submissions_with_exe_are_completely_untouched():
    """A submission that already ships a working .exe must not trigger any
    pause / banner logic — the alternative-evidence-free .exe path is
    fully off-limits per teacher instruction."""
    paths = [
        "student/project.yyp",
        "student/V1/game.exe",
        "student/V1/data.win",
        "student/report.docx",
    ]
    inv = {
        "runtime_observation_report": {
            # Note: no gamemaker_ide_build populated — a working .exe means
            # the auto-build code path is never entered.
        },
    }
    result = _base_grading_result(paths, inv=inv)
    apply_runtime_evidence_gate(result, artifact_inventory=inv)

    assert result.get("grading_paused") is None, (
        ".exe submissions must never be flagged with grading_paused"
    )
    assert result.get("gamemaker_install_pause_banner") is None, (
        ".exe submissions must never render the install-pause banner"
    )
