"""Scratch .sb3 must appear in academic diagnostics as game file + source."""
from __future__ import annotations

from pathlib import Path

from app.academic_explainability import build_missing_evidence_diagnostics
from app.artifact_inventory import build_artifact_inventory
from app.explainability_migration import _rebuild_diagnostics_for_ui
from app.grading_mode_policy import enrich_artifact_inventory_from_snapshot_meta


def test_build_inventory_detects_sb3_as_executable_and_source(tmp_path: Path):
    sb3 = tmp_path / "Scrath file.sb3"
    sb3.write_bytes(b"PK-scratch")
    doc = tmp_path / "report.docx"
    doc.write_bytes(b"doc")

    # fast mode skips Scratch runtime execution — we only assert static detection here.
    inv = build_artifact_inventory(
        main_document_path=str(doc),
        submission_paths=[str(doc), str(sb3)],
        student_name="student",
        grading_mode="fast",
        skip_runtime_observation=True,
        skip_heavy_enrichment=True,
    )
    assert inv["has_executable_artifacts"] is True
    assert inv["has_source_code_artifacts"] is True
    assert (inv.get("runtime_artifacts") or {}).get("scratch_detected") is True

    diag = build_missing_evidence_diagnostics(inv, grading_mode="deep")
    by_req = {r["requirement_ar"]: r for r in diag["rows"]}
    # .sb3 is detected (no longer "مفقود"), but runtime stays unverified → present False.
    assert "مفقود" not in by_req["ملف اللعبة (exe/build)"]["status_ar"]
    assert "Scratch" in by_req["ملف اللعبة (exe/build)"]["status_ar"]
    assert by_req["تغطية الكود المصدري"]["present"] is True


def test_slim_snapshot_enrichment_restores_scratch_from_submission_paths():
    snapshot = {
        "grading_mode": "deep",
        "submission_paths": [
            r"uploads\students\bx46\العاب قبل التعديل\Scrath file.sb3",
            r"uploads\students\bx46\العاب قبل التعديل\اجدد اشي.docx",
        ],
        "content_fingerprint": {"word_count": 4832, "image_count": 3},
        "artifact_inventory": {},
    }
    inv = enrich_artifact_inventory_from_snapshot_meta({}, snapshot)
    diag = _rebuild_diagnostics_for_ui({**snapshot, "artifact_inventory": inv})
    by_req = {r["requirement_ar"]: r for r in diag["rows"]}
    assert "مفقود" not in by_req["ملف اللعبة (exe/build)"]["status_ar"]
    assert "Scratch" in by_req["ملف اللعبة (exe/build)"]["status_ar"]
    assert by_req["تغطية الكود المصدري"]["present"] is True
