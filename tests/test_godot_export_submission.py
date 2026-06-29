"""Godot export-only submissions (exe/pck without loose .gd)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestGodotExportOnlySubmission(unittest.TestCase):
    def test_pck_augmented_source_and_coverage(self):
        from app.artifact_inventory import build_artifact_inventory
        from app.academic_explainability import build_extraction_coverage_metrics
        from app.runtime_engines.registry import resolve_engine

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "student demo"
            root.mkdir()
            exe_dir = root / "exe"
            exe_dir.mkdir()
            pck = exe_dir / "game.pck"
            pck.write_bytes(
                b"\0" * 20
                + b"GDPC"
                + b"\0" * 40
                + b"res://main.tscn\x00player.gd\x00enemy.gd\x00"
            )
            (exe_dir / "game.exe").write_bytes(b"MZ" + b"\0" * 64)
            (root / "report.docx").write_bytes(b"PK\x03\x04")

            paths = [
                str((root / "report.docx").resolve()),
                str(pck.resolve()),
                str((exe_dir / "game.exe").resolve()),
            ]
            inv = build_artifact_inventory(
                main_document_path=paths[0],
                submission_paths=paths,
                student_name="student demo",
            )
            self.assertTrue(inv.get("has_source_code_artifacts"))
            src_files = (inv.get("source_code") or {}).get("files") or []
            self.assertTrue(any(f.get("source_kind") == "godot_pck_embedded" for f in src_files))

            cov = build_extraction_coverage_metrics(
                submission_paths=paths,
                inventory=inv,
            )
            self.assertGreater(cov.get("coverage_ratio", 0), 0.0)
            self.assertFalse(cov.get("weak_analysis_risk"))

            engine = resolve_engine(root)
            self.assertIsNotNone(engine)
            self.assertEqual(engine.engine_id, "godot")

    def test_editor_bundle_skipped_in_expand(self):
        from app.evidence_completeness_gate import expand_submission_paths

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "ali"
            root.mkdir()
            tools = root / "أدوات التصدير"
            tools.mkdir()
            editor = tools / "Godot_v4.6-stable_win64.exe"
            editor.write_bytes(b"MZ" + b"\0" * 200)
            modules = tools / "modules"
            modules.mkdir()
            (modules / "noise.cs").write_text("namespace Godot;", encoding="utf-8")
            run = root / "exe"
            run.mkdir()
            (run / "game.pck").write_bytes(b"GDPC" + b"\0" * 80 + b".gd")
            (run / "game.exe").write_bytes(b"MZ" + b"\0" * 64)

            expanded = expand_submission_paths(
                [str((root / "exe" / "game.exe").resolve())],
                primary_path=str((root / "exe" / "game.exe").resolve()),
                student_name="ali",
            )
            lowered = " ".join(expanded).lower()
            self.assertNotIn("noise.cs", lowered)
            self.assertIn("game.pck", lowered)


if __name__ == "__main__":
    unittest.main()
