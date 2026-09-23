"""Regression net for the authoritative gameplay_verification (GV) pipeline.

Rebuilt 2026-07-06. Covers resolve/sync, blob preference, Arabic wording,
attach_grading_mode_metadata, snapshot compaction. Deterministic; no runtime.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.gameplay_verifier import (  # noqa: E402
    _gameplay_verification_blob,
    calculate_l4_level,
    format_agent_play_summary_ar,
    resolve_authoritative_gameplay_verification,
    sync_authoritative_gv,
)


def weak_l3_gv() -> dict:
    return {
        "gameplay_entered": False,
        "l4_level": "L3",
        "menu_navigation": {"status": "menu_only"},
    }


def rich_l4_gv() -> dict:
    return {
        "gameplay_entered": True,
        "l4_level": "L4_partial",
        "player_movement_verified": True,
        "visual_delta_score": 0.42,
        "menu_navigation": {"status": "entered_gameplay"},
        "evidence_package": {"frames": 6},
        "criterion_pass_p5": True,
        "criterion_pass_p6": True,
    }


def inventory_with_nested_rich_gv() -> dict:
    return {
        "gameplay_verification": weak_l3_gv(),
        "runtime_observation_report": {
            "status": "completed",
            "gameplay_verification": weak_l3_gv(),
            "signals": {
                "runtime_launch_attempted": True,
                "godot_observation": {
                    "gameplay_verification": rich_l4_gv(),
                },
            },
        },
    }


class TestResolveAuthoritative:
    def test_picks_rich_nested_over_weak_top_level(self):
        gv = resolve_authoritative_gameplay_verification(
            artifact_inventory=inventory_with_nested_rich_gv(), grading_result={}
        )
        assert gv.get("gameplay_entered") is True
        assert gv.get("l4_level") == "L4_partial"

    def test_empty_inputs_return_empty(self):
        assert resolve_authoritative_gameplay_verification(
            artifact_inventory={}, grading_result={}
        ) == {}

    def test_does_not_mutate_inputs(self):
        inv = inventory_with_nested_rich_gv()
        snapshot = copy.deepcopy(inv)
        resolve_authoritative_gameplay_verification(artifact_inventory=inv, grading_result={})
        assert inv == snapshot


class TestSyncAuthoritativeGV:
    def test_sync_writes_rich_gv_everywhere(self):
        inv = inventory_with_nested_rich_gv()
        result: dict = {}
        assert sync_authoritative_gv(inv, result) is True
        for holder in (
            result["gameplay_verification"],
            inv["gameplay_verification"],
            inv["runtime_observation_report"]["gameplay_verification"],
        ):
            assert holder["gameplay_entered"] is True
            assert holder["l4_level"] == "L4_partial"
        assert result["artifact_inventory"] is inv

    def test_sync_no_gv_returns_false(self):
        result: dict = {}
        assert sync_authoritative_gv({}, result) is False
        assert "gameplay_verification" not in result

    def test_sync_never_downgrades_existing_rich_result(self):
        result = {"gameplay_verification": rich_l4_gv()}
        sync_authoritative_gv({"gameplay_verification": weak_l3_gv()}, result)
        assert result["gameplay_verification"]["l4_level"] == "L4_partial"
        assert result["gameplay_verification"]["gameplay_entered"] is True


class TestBlobPreference:
    def test_result_gv_wins_over_all(self):
        blob = _gameplay_verification_blob(
            None,
            inventory={"gameplay_verification": weak_l3_gv()},
            grading_result={"gameplay_verification": rich_l4_gv()},
        )
        assert blob["l4_level"] == "L4_partial"
        assert blob["gameplay_entered"] is True

    def test_inventory_gv_used_when_result_empty(self):
        blob = _gameplay_verification_blob(
            None, inventory={"gameplay_verification": rich_l4_gv()}, grading_result={}
        )
        assert blob["gameplay_entered"] is True

    def test_synced_inventory_wins_over_stale_observation(self):
        blob = _gameplay_verification_blob(
            {"gameplay_verification": weak_l3_gv()},
            inventory={"gameplay_verification": rich_l4_gv()},
            grading_result={},
        )
        assert blob["l4_level"] == "L4_partial"
        assert blob["gameplay_entered"] is True

    def test_after_sync_blob_matches_authoritative(self):
        inv = inventory_with_nested_rich_gv()
        result: dict = {}
        sync_authoritative_gv(inv, result)
        blob = _gameplay_verification_blob(
            inv.get("runtime_observation_report"), inventory=inv, grading_result=result
        )
        assert blob["l4_level"] == "L4_partial"
        assert blob["gameplay_entered"] is True


class TestAgentPlaySummaryWording:
    def test_l4_partial_open_gate_wording(self):
        label = format_agent_play_summary_ar("L4", rich_l4_gv())
        assert "L4 جزئي" in label
        assert "Gate مفتوح" in label

    def test_l4_full_wording(self):
        gv = rich_l4_gv()
        gv["l4_level"] = "L4_full"
        assert "L4 كامل" in format_agent_play_summary_ar("L4", gv)

    def test_launch_only_is_honest_not_misleading(self):
        label = format_agent_play_summary_ar("L3", {"l4_level": "L3"})
        assert "تم تشغيل ملف اللعبة" in label
        assert "لم يتم إثبات" in label

    def test_gameplay_entered_false_states_reason(self):
        label = format_agent_play_summary_ar(
            "L3",
            {"gameplay_entered": False, "menu_navigation": {"status": "menu_stuck"}},
        )
        assert label.startswith("لا")
        assert "menu_stuck" in label

    def test_l4_claim_without_entry_is_not_confirmed(self):
        label = format_agent_play_summary_ar(
            "L4", {"l4_level": "L4_partial", "gameplay_entered": None}
        )
        assert "غير مؤكد" in label
        assert not label.startswith("نعم")

    def test_failure_reason_takes_priority(self):
        label = format_agent_play_summary_ar(
            "L3",
            {
                "failure_reason_code": "PROCESS_CRASHED",
                "failure_reason_ar": "انهيار العملية عند الإقلاع",
            },
        )
        assert label.startswith("لا — PROCESS_CRASHED")


class TestL4Invariants:
    def test_no_l4_without_gameplay_entered(self):
        assert calculate_l4_level(gameplay_entered=False, mechanics_verified_count=5) == "L3"

    def test_partial_needs_one_mechanic(self):
        assert calculate_l4_level(gameplay_entered=True, mechanics_verified_count=1) == "L4_partial"

    def test_full_needs_three_mechanics(self):
        assert calculate_l4_level(gameplay_entered=True, mechanics_verified_count=3) == "L4_full"

    def test_entered_with_no_mechanics_stays_l3(self):
        assert calculate_l4_level(gameplay_entered=True, mechanics_verified_count=0) == "L3"


class TestAttachGradingModeMetadata:
    def test_profile_meta_uses_authoritative_gv(self):
        from app.core.grading_profiles import attach_grading_mode_metadata

        out = attach_grading_mode_metadata(
            {"artifact_inventory": inventory_with_nested_rich_gv()}, "pro"
        )
        meta = out["grading_profile"]
        assert meta["l4_level"] == "L4_partial"
        assert "L4 جزئي" in (meta.get("agent_play_label_ar") or "")
        assert "إطلاق ملف فقط" not in (meta.get("agent_play_label_ar") or "")
        assert out["gameplay_verification"]["gameplay_entered"] is True

    def test_weak_only_evidence_stays_honest(self):
        from app.core.grading_profiles import attach_grading_mode_metadata

        out = attach_grading_mode_metadata(
            {
                "artifact_inventory": {
                    "gameplay_verification": weak_l3_gv(),
                    "runtime_observation_report": {
                        "status": "completed",
                        "gameplay_verification": weak_l3_gv(),
                    },
                }
            },
            "pro",
        )
        meta = out["grading_profile"]
        assert meta["l4_level"] in ("L3", None)
        assert "Gate مفتوح" not in (meta.get("agent_play_label_ar") or "")


class TestCompactSnapshot:
    def test_pro_deep_mode_is_passthrough(self):
        from app.grading_mode_policy import compact_snapshot_for_storage

        snap = {
            "grade_level": "P",
            "gameplay_verification": rich_l4_gv(),
            "artifact_inventory": inventory_with_nested_rich_gv(),
        }
        out = compact_snapshot_for_storage(snap, "deep")
        assert out["gameplay_verification"]["l4_level"] == "L4_partial"
        assert out["gameplay_verification"]["gameplay_entered"] is True

    def test_fast_mode_keeps_gameplay_verification(self):
        from app.grading_mode_policy import compact_snapshot_for_storage

        snap = {
            "grade_level": "P",
            "gameplay_verification": rich_l4_gv(),
            "artifact_inventory": inventory_with_nested_rich_gv(),
            "criteria_results": [],
        }
        out = compact_snapshot_for_storage(snap, "fast")
        assert (out.get("gameplay_verification") or {}).get("gameplay_entered") is True
