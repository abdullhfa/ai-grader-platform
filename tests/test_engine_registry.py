"""Registry tests — ensure all engines load regardless of import order."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestEngineRegistry(unittest.TestCase):
    def test_unity_import_still_resolves_gamemaker(self):
        import importlib

        reg = importlib.import_module("app.runtime_engines.registry")
        importlib.reload(reg)
        importlib.import_module("app.runtime_engines.unity.engine")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Game.yyp").write_text('{"resourceType":"GMProject","resources":[]}', encoding="utf-8")
            (root / "objects" / "obj_a").mkdir(parents=True)
            (root / "objects" / "obj_a" / "Create_0.gml").write_text("// demo", encoding="utf-8")

            from app.runtime_engines.gamemaker.engine import GameMakerRuntimeEngine

            resolved = reg.resolve_engine(root)
            self.assertIs(resolved, GameMakerRuntimeEngine)


if __name__ == "__main__":
    unittest.main()
