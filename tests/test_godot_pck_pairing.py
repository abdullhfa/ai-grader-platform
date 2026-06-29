"""Godot PCK pairing and runtime evidence promotion tests."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_pairing_final_pck_without_final_exe():
    from app.runtime_engines.godot.export_runner import (
        cleanup_pck_pairing,
        resolve_pck_exe_pairing,
    )

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        exe_dir = root / "exe"
        exe_dir.mkdir()
        donor = exe_dir / "farst game.exe"
        donor.write_bytes(b"MZ" + b"\0" * 128)
        pck = exe_dir / "final.pck"
        pck.write_bytes(b"GDPC" + b"\0" * 2000)

        pairing = resolve_pck_exe_pairing(root, session_id="test_pair")
        meta = pairing["pairing_meta"]
        assert meta.get("paired") is True
        assert pairing["paired_executable"] is not None
        assert pairing["paired_executable"].name.lower() == "final.exe"
        assert pairing["pck"].name.lower() == "final.pck"
        assert (pairing["run_cwd"] / "final.pck").is_file()
        cleanup_pck_pairing(meta)


def test_promotion_tier_b_with_screenshots():
    from app.runtime_evidence_promotion import assess_runtime_evidence_promotion

    promo = assess_runtime_evidence_promotion(
        {
            "runtime_observed": True,
            "legacy_observation": {"smoke_result": "stable_window"},
            "runtime_screenshots": [
                {"status": "captured", "visual_state": "unknown"},
                {"status": "captured", "visual_state": "gameplay_candidate"},
            ],
        }
    )
    assert promo["partial_runtime_verified"] is True
    assert promo["min_confidence_tier"] == "B"


def test_godot_engine_wins_over_legacy():
    from app.runtime_engines.godot.engine import GodotRuntimeEngine
    from app.runtime_engines.legacy.engine import LegacyExecutableEngine

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        exe_dir = root / "exe"
        exe_dir.mkdir()
        (exe_dir / "game.exe").write_bytes(b"MZ" + b"\0" * 128)
        (exe_dir / "final.pck").write_bytes(b"GDPC" + b"\0" * 1500)
        assert GodotRuntimeEngine.detect(root) > LegacyExecutableEngine.detect(root)
