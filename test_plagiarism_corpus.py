"""Plagiarism corpus vs AI detection scope."""
from __future__ import annotations

from pathlib import Path

from app.graders.game_analyzer import build_plagiarism_corpus
from app.grading_mode_policy import extract_fast_grading_text, resolve_word_document_paths


def test_plagiarism_corpus_includes_code_and_vision(tmp_path: Path):
    code_file = tmp_path / "player.gd"
    code_file.write_text('extends Node\nfunc _ready():\n    print("hello")', encoding="utf-8")
    corpus = build_plagiarism_corpus(
        "Word report body about the game design.",
        [str(code_file)],
        vision_analysis_text="Screenshot shows menu and score HUD.",
    )
    assert "Word report body" in corpus
    assert "player.gd" in corpus
    assert "extends Node" in corpus
    assert "Screenshot shows menu" in corpus


def test_word_paths_exclude_code(tmp_path: Path):
    doc = tmp_path / "report.docx"
    doc.write_bytes(b"not a real docx")
    code = tmp_path / "main.gd"
    code.write_text("var x = 1", encoding="utf-8")
    paths = resolve_word_document_paths(str(doc), [str(code)])
    assert str(doc.resolve()) in paths
    assert str(code.resolve()) not in paths


def test_extract_fast_grading_text_empty_without_doc(tmp_path: Path):
    code = tmp_path / "only.gd"
    code.write_text("print(1)", encoding="utf-8")
    text, imgs = extract_fast_grading_text(str(code), [str(code)])
    assert text == ""
    assert imgs == 0
