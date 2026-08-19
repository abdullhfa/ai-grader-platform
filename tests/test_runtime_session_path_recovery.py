from pathlib import Path

from app.explainability_migration import _submission_paths_from_snapshot


def test_docx_submission_recovers_matching_runtime_session_tree(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    submission_doc = uploads / "Ahmed Osman" / "submission.docx"
    submission_doc.parent.mkdir(parents=True)
    submission_doc.write_bytes(b"docx-placeholder")

    runtime_session = uploads / "runtime_sessions" / "Ahmed Osman"
    runtime_session.mkdir(parents=True)
    (runtime_session / "project.yyp").write_text("{}", encoding="utf-8")
    (runtime_session / "gameplay.webm").write_bytes(b"webm-placeholder")

    paths = _submission_paths_from_snapshot(
        {"student_name": "Ahmed Osman"},
        str(submission_doc),
        "Ahmed Osman",
    )

    assert str(runtime_session) in paths
    assert any(Path(path).name == "Ahmed Osman" for path in paths)
