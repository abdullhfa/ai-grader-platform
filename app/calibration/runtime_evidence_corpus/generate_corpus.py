"""
Generate runtime evidence calibration corpus (50–100 cases).

Tests governability — NOT grading accuracy:
  L2 ingestion, asset exclusion, video authority leakage, contradiction visibility.
"""
from __future__ import annotations

import argparse
import json
import struct
import zlib
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

CORPUS_ROOT = Path(__file__).resolve().parent
CASES_DIR = CORPUS_ROOT / "cases"
EXPECTED_PATH = CORPUS_ROOT / "expected_cases.json"

# Minimal valid 1x1 PNG
_MIN_PNG = (
    b"\x89PNG\r\n\x1a\n"
    + struct.pack(">I", 13)
    + b"IHDR"
    + struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    + struct.pack(">I", zlib.crc32(b"IHDR" + struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) & 0xFFFFFFFF)
    + struct.pack(">I", 0)
    + b"IEND"
    + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
)


def _write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_MIN_PNG)


def _write_text(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or "stub", encoding="utf-8")


def _write_gd(path: Path) -> None:
    _write_text(path, 'extends Node\nfunc _ready():\n    pass\n')


ARCHETYPE_BUILDERS: Dict[str, Callable[[Path], Dict[str, Any]]] = {}


def _register(name: str):
    def deco(fn: Callable[[Path], Dict[str, Any]]):
        ARCHETYPE_BUILDERS[name] = fn
        return fn
    return deco


@_register("l0_doc_only")
def _l0_doc_only(case_dir: Path) -> Dict[str, Any]:
    _write_text(case_dir / "docs" / "gdd.docx", "GDD stub document")
    return {
        "runtime_level_max": 1,
        "l2_count_max": 0,
        "expect_ambiguity_min": 0,
        "expect_contradictions_when_exe": False,
    }


@_register("l1_exe_only")
def _l1_exe_only(case_dir: Path) -> Dict[str, Any]:
    _write_text(case_dir / "build" / "game.exe", "MZ stub")
    return {
        "runtime_level_min": 1,
        "l2_count_max": 0,
        "expect_ambiguity_min": 0,
        "expect_contradictions_when_exe": True,
    }


@_register("l1_godot_export")
def _l1_godot_export(case_dir: Path) -> Dict[str, Any]:
    _write_text(case_dir / "game.pck", "PK stub")
    _write_text(case_dir / "game.exe", "MZ stub")
    _write_text(case_dir / "project.godot", "config_version=5")
    return {
        "runtime_level_min": 1,
        "l2_count_max": 0,
        "expect_ambiguity_min": 1,
        "expect_contradictions_when_exe": True,
    }


@_register("l2_screenshot_folder")
def _l2_screenshot_folder(case_dir: Path) -> Dict[str, Any]:
    _write_png(case_dir / "صور تشغيل اللعبة" / "menu_screen.png")
    _write_png(case_dir / "صور تشغيل اللعبة" / "hud_score.png")
    _write_png(case_dir / "مشروع Godot" / "assets" / "bg001.png")
    _write_png(case_dir / "مشروع Godot" / "sprites" / "player.png")
    return {
        "runtime_level_min": 2,
        "l2_count_min": 2,
        "l2_count_max": 2,
        "godot_assets_excluded": True,
        "expect_ambiguity_min": 0,
    }


@_register("l2_mixed_with_exe")
def _l2_mixed_with_exe(case_dir: Path) -> Dict[str, Any]:
    _l2_screenshot_folder(case_dir)
    _write_text(case_dir / "build" / "P_03.exe", "MZ stub")
    return {
        "runtime_level_min": 2,
        "l2_count_min": 2,
        "godot_assets_excluded": True,
        "expect_ambiguity_min": 2,
        "expect_contradictions_when_exe": True,
    }


@_register("l3_video_only")
def _l3_video_only(case_dir: Path) -> Dict[str, Any]:
    _write_text(case_dir / "فيديو اللعبة" / "gameplay_demo.mp4", "fake mp4")
    return {
        "runtime_level_min": 1,
        "expect_video_detected": True,
        "expect_ambiguity_min": 1,
    }


@_register("l3_orphan_video")
def _l3_orphan_video(case_dir: Path) -> Dict[str, Any]:
    _write_text(case_dir / "recordings" / "playthrough.webm", "fake webm")
    return {
        "runtime_level_min": 1,
        "expect_video_detected": True,
        "expect_ambiguity_min": 1,
        "expect_orphan_video_flag": True,
    }


@_register("l1_l2_l3_full")
def _l1_l2_l3_full(case_dir: Path) -> Dict[str, Any]:
    _l2_mixed_with_exe(case_dir)
    _write_text(case_dir / "فيديو اللعبة بعد التعديل.mp4", "fake mp4")
    _write_gd(case_dir / "src" / "player.gd")
    return {
        "runtime_level_min": 2,
        "l2_count_min": 2,
        "expect_video_detected": True,
        "expect_ambiguity_min": 2,
        "expect_contradictions_when_exe": True,
    }


@_register("godot_assets_only")
def _godot_assets_only(case_dir: Path) -> Dict[str, Any]:
    for i in range(8):
        _write_png(case_dir / "مشروع Godot" / "assets" / f"tile_{i}.png")
    _write_text(case_dir / "project.godot", "config_version=5")
    return {
        "runtime_level_max": 2,
        "l2_count_max": 0,
        "godot_assets_excluded": True,
    }


@_register("l2_screenshots_path_markers")
def _l2_screenshots_en(case_dir: Path) -> Dict[str, Any]:
    _write_png(case_dir / "screenshots" / "gameplay" / "level1.png")
    _write_png(case_dir / "runtime_evidence" / "capture_01.png")
    return {
        "runtime_level_min": 2,
        "l2_count_min": 2,
    }


@_register("l2_no_testing_docs")
def _l2_no_testing_docs(case_dir: Path) -> Dict[str, Any]:
    _l2_screenshot_folder(case_dir)
    _write_text(case_dir / "docs" / "design_survey.docx", "design only — no test logs")
    return {
        "runtime_level_min": 2,
        "l2_count_min": 2,
        "expect_ambiguity_min": 1,
        "expect_flag": "l2_visual_without_structured_testing",
    }


# Distribution for 80 cases
ARCHETYPE_COUNTS: List[Tuple[str, int]] = [
    ("l0_doc_only", 6),
    ("l1_exe_only", 8),
    ("l1_godot_export", 8),
    ("l2_screenshot_folder", 12),
    ("l2_mixed_with_exe", 10),
    ("l3_video_only", 8),
    ("l3_orphan_video", 8),
    ("l1_l2_l3_full", 10),
    ("godot_assets_only", 6),
    ("l2_screenshots_path_markers", 6),
    ("l2_no_testing_docs", 8),
]


def generate_corpus(*, count: int = 80, clean: bool = False) -> Dict[str, Any]:
    if clean and CASES_DIR.exists():
        import shutil
        shutil.rmtree(CASES_DIR)
    CASES_DIR.mkdir(parents=True, exist_ok=True)

    cases: List[Dict[str, Any]] = []
    idx = 0
    for archetype, n in ARCHETYPE_COUNTS:
        builder = ARCHETYPE_BUILDERS[archetype]
        for j in range(n):
            if idx >= count:
                break
            idx += 1
            case_id = f"{archetype}_{j + 1:03d}"
            case_dir = CASES_DIR / case_id
            case_dir.mkdir(parents=True, exist_ok=True)
            expect = builder(case_dir)
            cases.append({
                "case_id": case_id,
                "archetype": archetype,
                "expect": {
                    **expect,
                    "authority_auto_inferred": False,
                    "claims_registry_complete": True,
                    "replay_has_claim_boundary": True,
                },
            })
        if idx >= count:
            break

    manifest = {
        "corpus_id": "runtime_evidence_calibration_v1",
        "freeze": "GOVERNANCE_FREEZE_v1",
        "purpose_ar": "اختبار governability — ليس grading accuracy",
        "case_count": len(cases),
        "invariants_tested": [
            "l2_screenshot_ingestion",
            "engine_asset_exclusion",
            "video_no_authority_leakage",
            "contradictions_visible",
            "runtime_claim_contract_complete",
            "replay_claim_boundary",
        ],
        "cases": cases,
    }
    EXPECTED_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate runtime evidence calibration corpus")
    parser.add_argument("--count", type=int, default=80)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    manifest = generate_corpus(count=args.count, clean=args.clean)
    print(f"Generated {manifest['case_count']} cases -> {EXPECTED_PATH}")


if __name__ == "__main__":
    main()
