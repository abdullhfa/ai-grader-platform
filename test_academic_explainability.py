"""Academic explainability layer — governance + diagnostics."""
from __future__ import annotations

from app.academic_explainability import (
    attach_academic_explainability,
    build_governance_intent_explanation,
    build_missing_evidence_diagnostics,
)


def test_governance_gated_not_system_failure():
    inv = {
        "executable_artifacts": {"files": [{"name": "game.exe"}]},
        "runtime_observation_report": {
            "status": "gated",
            "reason": "GOVERNANCE_FREEZE_v1_active",
            "gate_ar": "L4 sandbox مقفول",
        },
        "runtime_evidence_level": {"level": 1, "authority": "artifact_acknowledgment_only"},
    }
    gov = build_governance_intent_explanation(inv)
    assert gov["runtime_execution_ar"] == "معطّل بحكم الحوكمة"
    assert gov["automatic_achievement_allowed"] is False
    assert "قرار حوكمة" in gov["not_a_system_failure_ar"]


def test_missing_evidence_exe_only():
    inv = {
        "documentation": {"status": "not_detected", "files": []},
        "source_code": {"status": "not_detected", "files": []},
        "executable_artifacts": {
            "files": [{"name": "My project (3).exe"}],
            "runtime_verified": False,
        },
        "runtime_artifacts": {"executables_detected": True},
        "runtime_observation_report": {"status": "gated"},
        "extraction_coverage": {
            "detected_cs_files_ingested": 5,
            "estimated_project_cs_files": 184,
            "coverage_ratio": 0.027,
            "weak_analysis_risk": True,
        },
    }
    diag = build_missing_evidence_diagnostics(inv)
    assert diag["missing_count"] >= 4
    rows = {r["requirement_ar"]: r for r in diag["rows"]}
    assert rows["ملف اللعبة (exe/build)"]["present"] is True
    assert rows["تقرير Word/PDF"]["present"] is False


def test_attach_populates_blocks():
    inv = {
        "documentation": {"status": "not_detected", "files": []},
        "source_code": {"status": "not_detected", "files": []},
        "executable_artifacts": {"files": [{"name": "g.exe"}]},
        "runtime_observation_report": {"status": "gated", "reason": "GOVERNANCE_FREEZE_v1_active"},
    }
    out = attach_academic_explainability(inv, submission_paths=[])
    assert "governance_intent" in out
    assert "missing_evidence_diagnostics" in out
    assert "extraction_coverage" in out


def test_basic_pro_upgrade_labels():
    inv = {
        "grading_mode_note_ar": "وضع BASIC — تقييم سريع",
        "runtime_observation_report": {"status": "skipped_fast_mode"},
        "documentation": {"status": "analyzed", "files": [{"name": "g.docx", "ext": ".docx"}]},
        "source_code": {"status": "detected", "files": [{"name": "main.gd", "ext": ".gd"}]},
        "has_source_code_artifacts": True,
        "embedded_screenshots": {"count": 5},
        "vision_analysis_used": True,
        "executable_artifacts": {"files": []},
        "testing_evidence": {"status": "not_detected"},
    }
    diag = build_missing_evidence_diagnostics(inv, grading_mode="fast")
    rows = {r["requirement_ar"]: r for r in diag["rows"]}
    assert rows["ملف اللعبة (exe/build)"]["status_ar"] == "تحديث الى خطة برو"
    assert rows["أدلة الاختبار (خطط/سجلات)"]["status_ar"] == "تحديث الى خطة برو"
    assert rows["التحقق من الصور والفيديو"]["status_ar"].startswith("أساسي:")
    assert rows["التحقق من التشغيل (runtime)"]["status_ar"] == "تحديث الى خطة برو"
    assert rows["تقرير Word/PDF"]["status_ar"] == "تم التدقيق"
    assert rows["حالة الأدلة البصرية (Vision)"]["present"] is False


def test_sanitize_diagnostics_removes_retired_rows():
    from app.academic_explainability import sanitize_missing_evidence_diagnostics_for_ui

    diag = {
        "version": 1,
        "rows": [
            {"requirement_ar": "تقرير Word/PDF (GDD/توثيق)", "present": True, "status_ar": "تم التدقيق"},
            {"requirement_ar": "Web Runtime Browser Automation", "present": True, "status_ar": "غير متوفر (لا HTML)"},
            {"requirement_ar": "Android Emulator Farm (Flutter/Kotlin/Java)", "present": True, "status_ar": "غير متوفر (لا Android)"},
            {"requirement_ar": "GameMaker Runtime Verification", "present": True, "status_ar": "غير متوفر (لا GameMaker)"},
            {"requirement_ar": "Scratch Verification", "present": True, "status_ar": "غير متوفر (لا Scratch)"},
        ],
        "missing_count": 0,
        "missing_items_ar": [],
    }
    out = sanitize_missing_evidence_diagnostics_for_ui(diag)
    assert out is not None
    reqs = [r["requirement_ar"] for r in out["rows"]]
    assert reqs == ["تقرير Word/PDF"]


def test_pro_media_verification_when_vision_ran():
    inv = {
        "grading_mode_note_ar": "وضع PRO",
        "runtime_observation_report": {"status": "completed"},
        "documentation": {"status": "analyzed", "files": [{"name": "g.docx", "ext": ".docx"}]},
        "embedded_screenshots": {"count": 3},
        "vision_analysis_used": True,
        "gameplay_video_inference": {"videos_analyzed": 0},
    }
    diag = build_missing_evidence_diagnostics(inv, grading_mode="standard")
    rows = {r["requirement_ar"]: r for r in diag["rows"]}
    assert rows["التحقق من الصور والفيديو"]["present"] is True
    assert rows["التحقق من الصور والفيديو"]["status_ar"] == "تم (صور)"
