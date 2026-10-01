"""Provenance binding for runtime-gated criteria (P5, P6, M3).

Runtime evidence that opens a gate must say WHICH version, WHICH build and WHICH
source produced it.  This module only reads records that already exist
(``provenance`` and ``version_runtime_comparison``); it never merges V1 and V2 or
two different builds, and never re-runs anything.

Result: ``blocked[short] = {"status", "code", "detail"}`` for criteria whose runtime
evidence cannot be tied to an identifiable version/build.  Those criteria are
NOT VERIFIED (``NOT_VERIFIED_BLOCKED`` / ``PROVENANCE_MISMATCH``) — never verified,
and never a verdict against the student.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

GATED = ("P5", "P6", "M3")
GATING_VERSION = "V2"  # the submitted/improved version is the one the gate evaluates

STATUS_BLOCKED = "NOT_VERIFIED_BLOCKED"
STATUS_MISMATCH = "PROVENANCE_MISMATCH"


def _report(grading_result: Dict[str, Any]) -> Dict[str, Any]:
    inv = grading_result.get("artifact_inventory") or {}
    rep = inv.get("runtime_observation_report") or grading_result.get("runtime_observation_report")
    return rep if isinstance(rep, dict) else {}


def _exe_hash(prov: Optional[Dict[str, Any]]) -> Optional[str]:
    exe = ((prov or {}).get("build_provenance") or {}).get("executable") or {}
    return exe.get("sha256")


def evaluate_provenance_binding(grading_result: Dict[str, Any]) -> Dict[str, Any]:
    """Pure: which runtime-gated criteria have unattributable evidence."""
    report = _report(grading_result)
    prov = report.get("provenance")
    comparison = report.get("version_runtime_comparison")
    out: Dict[str, Any] = {
        "applies": False, "blocked": {}, "bound_version": None,
        "build_sha256": None, "source_tree_hash": None,
    }
    if not isinstance(prov, dict) and not isinstance(comparison, dict):
        return out  # legacy/stored data without provenance: nothing to bind
    out["applies"] = True

    def block(shorts, status, code, detail):
        for short in shorts:
            out["blocked"].setdefault(short, {"status": status, "code": code, "detail": detail})

    if isinstance(prov, dict):
        if prov.get("error"):
            block(GATED, STATUS_BLOCKED, "provenance_unavailable", str(prov["error"])[:160])
        else:
            build = prov.get("build_provenance") or {}
            exe = build.get("executable") or {}
            if build.get("kind") in ("student_supplied", "platform_built"):
                if not exe.get("exists", True) or (exe.get("sha256") is None and exe.get("hash_skipped") == "unreadable"):
                    block(GATED, STATUS_BLOCKED, "build_identity_unavailable",
                          "the executable that was run cannot be identified")
            out["bound_version"] = prov.get("version_label")
            out["build_sha256"] = exe.get("sha256")
            out["source_tree_hash"] = (prov.get("source_provenance") or {}).get("tree_hash")

    if isinstance(comparison, dict):
        status = comparison.get("status")
        if status == "PROVENANCE_MISMATCH":
            codes = ",".join(sorted({m.get("code", "") for m in comparison.get("provenance_mismatches") or []}))
            block(GATED, STATUS_MISMATCH, "version_provenance_mismatch", codes or "source/build mismatch")
        v2 = comparison.get("v2") or {}
        v1 = comparison.get("v1") or {}
        if isinstance(prov, dict) and not prov.get("error"):
            if prov.get("version_label") != GATING_VERSION:
                block(GATED, STATUS_BLOCKED, "gating_evidence_version_unbound",
                      f"runtime evidence is not bound to {GATING_VERSION} (bound to {prov.get('version_label')!r})")
            h_main, h_v2 = _exe_hash(prov), _exe_hash(v2.get("provenance"))
            if h_main and h_v2 and h_main != h_v2:
                block(GATED, STATUS_MISMATCH, "gating_build_differs_from_v2",
                      "the gating run's build is not the V2 build")
        # M3 is an improvement claim: it needs BOTH versions really run and distinct.
        if v1.get("run_state") != "RAN" or v2.get("run_state") != "RAN":
            if v2.get("run_state") == "RAN":
                block(("M3",), STATUS_BLOCKED, "v1_run_not_verified",
                      "V1 was not really run, so the V1→V2 improvement cannot be verified")
        elif status == "IDENTICAL_BUILD":
            block(("M3",), STATUS_BLOCKED, "identical_build_no_improvement_evidence",
                  "V1 and V2 are the same build")
    return out
