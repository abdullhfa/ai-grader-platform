"""Non-destructive explainability backfill tests."""
from __future__ import annotations

import copy

from app.explainability_migration import (
    apply_explainability_backfill,
    backfill_submission_record,
    build_explainability_revision_meta,
    compute_revision_snapshot_hash,
    extract_explainability_for_ui,
    preview_submission_backfill,
)


def test_backfill_preserves_grades():
    snap = {
        "grade_level": "U",
        "total_score": 0,
        "max_score": 100,
        "percentage": 0.0,
        "criteria_results": [
            {"criteria_level": "8/C.P5", "achieved": False, "score": 0},
        ],
        "artifact_inventory": {
            "executable_artifacts": {
                "files": [{"name": "game.exe", "path": "/tmp/game.exe"}],
                "runtime_verified": False,
            },
            "documentation": {"status": "not_detected", "files": []},
            "source_code": {"status": "not_detected", "files": []},
            "runtime_observation_report": {
                "status": "gated",
                "reason": "GOVERNANCE_FREEZE_v1_active",
            },
        },
        "file_path": "/tmp/game.exe",
    }
    before = copy.deepcopy(snap)
    updated, report = apply_explainability_backfill(snap)
    assert report["applied"] is True
    assert updated["grade_level"] == "U"
    assert updated["total_score"] == 0
    assert updated["criteria_results"][0]["achieved"] is False
    assert updated["explainability_revision"]["non_destructive"] is True
    rev = updated["explainability_revision"]
    assert rev["explainability_schema"] == "2.0"
    assert rev["policy_version"]
    assert rev["generated_by"] == "system"
    assert rev["trigger"] == "admin_backfill"
    assert rev["revision_type"] == "explainability_backfill"
    assert rev.get("snapshot_hash")
    assert rev.get("protected_digest") == report["protected_digest_before"]
    assert isinstance(updated.get("explainability_revision_history"), list)
    assert len(updated["explainability_revision_history"]) == 1
    assert updated["explainability_layer"].get("evidence_lineage")
    assert updated["explainability_layer"]["governance_intent"]
    ui = extract_explainability_for_ui(updated)
    assert ui and ui.get("governance_intent")


def test_backfill_skips_when_current():
    snap, _ = apply_explainability_backfill(
        {
            "grade_level": "P",
            "total_score": 50,
            "criteria_results": [],
            "artifact_inventory": {
                "runtime_observation_report": {"status": "gated"},
            },
        }
    )
    updated, report = apply_explainability_backfill(snap)
    assert report["skipped"] is True


class _FakeSub:
    id = 99
    student_name = "Test"
    submission_file_path = "/tmp/game.exe"
    grading_snapshot_json = None


def test_backfill_submission_no_snapshot():
    sub = _FakeSub()
    sub.grading_snapshot_json = None
    r = backfill_submission_record(sub, dry_run=True)
    assert r["skipped"] and r["reason"] == "no_snapshot"


def test_revision_lineage_chain_on_force():
    snap, _ = apply_explainability_backfill(
        {
            "grade_level": "P",
            "total_score": 50,
            "criteria_results": [],
            "artifact_inventory": {"runtime_observation_report": {"status": "gated"}},
        }
    )
    first_hash = snap["explainability_revision"]["snapshot_hash"]
    updated, report = apply_explainability_backfill(snap, force=True)
    assert report["applied"] is True
    assert updated["explainability_revision"]["previous_snapshot_hash"] == first_hash
    assert len(updated["explainability_revision_history"]) == 2


def test_preview_submission_backfill():
    sub = _FakeSub()
    sub.grading_snapshot_json = __import__("json").dumps(
        {
            "grade_level": "U",
            "total_score": 0,
            "criteria_results": [],
            "artifact_inventory": {"runtime_observation_report": {"status": "gated"}},
        }
    )
    row = preview_submission_backfill(sub)
    assert row["would_apply"] is True
    assert row["integrity_risk"] == "low"
    assert row["explainability_missing"] is True


def test_compute_revision_snapshot_hash_stable():
    layer = {"governance_intent": {"x": 1}}
    meta = build_explainability_revision_meta(
        protected_digest="abc",
        explainability_layer=layer,
    )
    h1 = compute_revision_snapshot_hash(meta, layer, "abc")
    h2 = compute_revision_snapshot_hash(meta, layer, "abc")
    assert h1 == h2
    assert meta["snapshot_hash"] == h1


def test_extract_ui_refreshes_stale_stored_diagnostics():
    snap = {
        "grading_mode": "fast",
        "execution_mode": "BASIC",
        "criteria_results": [],
        "criterion_authority": [],
        "visual_evidence_summary": {
            "images_found": 20,
            "images_analyzed": 20,
            "video_keyframes_found": 2,
            "video_keyframes_analyzed": 10,
        },
        "basic_video_keyframes_meta": {"videos_found": 2, "frames_extracted": 10},
        "artifact_inventory": {
            "grading_mode_note_ar": "وضع BASIC — تقييم سريع",
            "runtime_observation_report": {"status": "skipped_fast_mode"},
            "documentation": {"status": "analyzed", "files": [{"name": "g.docx", "ext": ".docx"}]},
            "source_code": {"status": "detected", "files": [{"name": "main.gd", "ext": ".gd"}]},
            "has_source_code_artifacts": True,
            "embedded_screenshots": {"count": 20},
            "vision_analysis_used": True,
            "executable_artifacts": {"files": []},
            "testing_evidence": {"status": "not_detected"},
            "visual_evidence_summary": {
                "images_found": 20,
                "images_analyzed": 20,
                "video_keyframes_found": 2,
                "video_keyframes_analyzed": 10,
            },
            "missing_evidence_diagnostics": {
                "version": 1,
                "rows": [
                    {"requirement_ar": "لقطات شاشة للعبة", "present": True, "status_ar": "موجود: 20 · مرسل: 30"},
                    {"requirement_ar": "Web Runtime Browser Automation", "present": True, "status_ar": "غير متوفر (لا HTML)"},
                    {"requirement_ar": "حالة الأدلة البصرية (Vision)", "present": True, "status_ar": "حلل 30 صورة"},
                    {"requirement_ar": "التحقق من الصور والفيديو", "present": True, "status_ar": "أساسي: 30 صورة + 5 إطار/فيديو"},
                    {"requirement_ar": "أدلة الاختبار (خطط/سجلات)", "present": False, "status_ar": "جزئي — Authority ✓"},
                ],
            },
        },
    }
    ui = extract_explainability_for_ui(snap)
    assert ui is not None
    reqs = [r["requirement_ar"] for r in ui["missing_evidence_diagnostics"]["rows"]]
    assert "لقطات شاشة للعبة" not in reqs
    assert "Web Runtime Browser Automation" not in reqs
    vision = next(r for r in ui["missing_evidence_diagnostics"]["rows"] if r["requirement_ar"] == "حالة الأدلة البصرية (Vision)")
    assert vision["status_ar"] == "تم تدقيق وتحليل 20 صورة"
    media = next(r for r in ui["missing_evidence_diagnostics"]["rows"] if r["requirement_ar"] == "التحقق من الصور والفيديو")
    assert media["status_ar"] == "عدد الفيديوهات : 2"


def test_stale_runtime_l4_diag_rebuilt_for_godot_without_launch():
    inv = {
        "grading_mode": "deep",
        "has_executable_artifacts": True,
        "documentation": {"status": "analyzed", "files": [{"ext": ".docx"}]},
        "executable_artifacts": {"status": "observed_structure_only", "files": [{"name": "game.apk"}]},
        "runtime_observation_report": {
            "status": "completed",
            "platform_analyses": [
                {
                    "signals": {
                        "runtime_method": "godot_static_analysis",
                        "pck_smoke": {"error": "godot_binary_not_configured"},
                    }
                }
            ],
        },
        "runtime_validation": {
            "functional_smoke": {"functional_smoke_pass": False, "reason": "structure_only_no_game_launch"},
        },
        "embedded_screenshots": {"count": 5, "vision_analyzed_count": 5},
        "visual_evidence_summary": {"images_found": 5, "images_analyzed": 5},
        "testing_evidence": {"status": "detected"},
    }
    snap = {
        "grading_mode": "deep",
        "artifact_inventory": inv,
        "explainability_layer": {
            "missing_evidence_diagnostics": {
                "rows": [
                    {
                        "requirement_ar": "التحقق من التشغيل (runtime)",
                        "present": True,
                        "status_ar": "تم التدقيق — ملاحظة L4 (تشغيل آلية، ليس تحققاً بشرياً L5)",
                    }
                ],
            },
        },
    }
    ui = extract_explainability_for_ui(snap)
    runtime = next(
        r for r in ui["missing_evidence_diagnostics"]["rows"]
        if r["requirement_ar"] == "التحقق من التشغيل (runtime)"
    )
    assert not runtime["present"]
    assert "لم تُشغَّل" in runtime["status_ar"]
