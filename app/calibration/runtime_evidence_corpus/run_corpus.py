"""
Run runtime evidence calibration corpus — governance invariants only.

Usage (repo root):
  python -m app.calibration.runtime_evidence_corpus.generate_corpus --count 80
  python -m app.calibration.runtime_evidence_corpus.run_corpus
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

CORPUS_ROOT = Path(__file__).resolve().parent
EXPECTED_PATH = CORPUS_ROOT / "expected_cases.json"
LAST_RUN_PATH = CORPUS_ROOT / "corpus_last_run.json"


def _collect_paths(case_dir: Path) -> List[str]:
    return [str(p.resolve()) for p in sorted(case_dir.rglob("*")) if p.is_file()]


def _run_single_case(case_dir: Path) -> Dict[str, Any]:
    from app.artifact_inventory import build_artifact_inventory
    from app.authority_replay import build_authority_replay
    from app.governance_drift_monitor import analyze_submission_governance_drift
    from app.project_intelligence.project_profile import build_project_profile

    paths = _collect_paths(case_dir)
    profile = build_project_profile(paths)
    inv = build_artifact_inventory(
        submission_paths=paths,
        project_profile=profile,
    )
    snap = {
        "artifact_inventory": inv,
        "authority_replay": build_authority_replay({"artifact_inventory": inv}),
    }
    drift = analyze_submission_governance_drift(snap)
    return {
        "profile": profile,
        "inventory": inv,
        "drift": drift,
        "replay": snap["authority_replay"],
    }


def _count_godot_asset_pngs(case_dir: Path) -> int:
    n = 0
    for p in case_dir.rglob("*.png"):
        blob = str(p).lower()
        if any(x in blob for x in ("godot", "assets", "sprites", "textures")):
            if "صور تشغيل" not in blob and "screenshot" not in blob and "runtime_evidence" not in blob:
                n += 1
    return n


def _evaluate_case(
    case_entry: Dict[str, Any],
    result: Dict[str, Any],
    case_dir: Path,
) -> Dict[str, Any]:
    expect = case_entry.get("expect") or {}
    inv = result["inventory"]
    l2l3 = inv.get("l2_l3_corroborative_runtime") or {}
    registry = inv.get("runtime_claims_registry") or {}
    rt_level = int((inv.get("runtime_evidence_level") or {}).get("level") or 0)
    l2_count = int(l2l3.get("l2_count") or 0)
    replay = result.get("replay") or {}
    steps = replay.get("steps") or []

    checks: List[Dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": ok, "detail": detail})

    if "runtime_level_min" in expect:
        check("runtime_level_min", rt_level >= int(expect["runtime_level_min"]), f"L{rt_level}")
    if "runtime_level_max" in expect:
        check("runtime_level_max", rt_level <= int(expect["runtime_level_max"]), f"L{rt_level}")
    if "l2_count_min" in expect:
        check("l2_count_min", l2_count >= int(expect["l2_count_min"]), f"l2={l2_count}")
    if "l2_count_max" in expect:
        check("l2_count_max", l2_count <= int(expect["l2_count_max"]), f"l2={l2_count}")

    if expect.get("godot_assets_excluded"):
        l2_paths = [
            str(x.get("path") or "").lower()
            for x in (l2l3.get("l2_folder_screenshots") or [])
            if isinstance(x, dict)
        ]
        leaked = any(
            any(m in p for m in ("مشروع godot", "/assets/", "/sprites/", "/textures/", ".godot"))
            and "صور تشغيل" not in p
            and "screenshots" not in p
            for p in l2_paths
        )
        check("godot_assets_excluded_from_l2", not leaked, f"l2_paths={len(l2_paths)}")

    amb_flags = l2l3.get("ambiguity_flags") or []
    if "expect_ambiguity_min" in expect:
        check(
            "ambiguity_flags_min",
            len(amb_flags) >= int(expect["expect_ambiguity_min"]),
            f"flags={len(amb_flags)}",
        )

    if expect.get("expect_flag"):
        found = any(
            isinstance(a, dict) and a.get("flag") == expect["expect_flag"]
            for a in amb_flags
        )
        check("expect_specific_flag", found, expect["expect_flag"])

    if expect.get("expect_orphan_video_flag"):
        rt = (result.get("profile") or {}).get("runtime_evidence") or {}
        l3v = l2l3.get("l3_video_evidence") or {}
        flags = rt.get("video_noise_flags") or []
        found = any(
            isinstance(f, dict) and f.get("flag") == "video_frames_extracted_without_runtime_linkage"
            for f in flags
        )
        check(
            "orphan_video_flag",
            found or int(l3v.get("videos_detected") or 0) > 0,
            str(flags),
        )

    check(
        "authority_auto_inferred_false",
        not l2l3.get("criterion_authority_auto_inferred"),
        str(l2l3.get("criterion_authority_auto_inferred")),
    )

    check(
        "claims_registry_complete",
        bool(registry.get("contract_complete")),
        str(registry.get("violations") or [])[:200],
    )

    has_boundary = any(s.get("phase") == "claim_boundary" for s in steps)
    check("replay_has_claim_boundary", has_boundary, f"steps={len(steps)}")

    if expect.get("expect_contradictions_when_exe"):
        has_contra = any(s.get("phase") == "contradiction" for s in steps)
        check("replay_shows_contradiction", has_contra, f"steps={len(steps)}")

    rt_level_ok = rt_level <= 3
    check("runtime_level_within_l0_l3", rt_level_ok, f"L{rt_level}")

    drift_status = (result.get("drift") or {}).get("status")
    check("no_critical_drift", drift_status != "critical_drift", drift_status or "")

    passed = sum(1 for c in checks if c["passed"])
    return {
        "case_id": case_entry.get("case_id"),
        "archetype": case_entry.get("archetype"),
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "all_passed": passed == len(checks),
        "observed": {
            "runtime_level": rt_level,
            "l2_count": l2_count,
            "ambiguity_flags": [a.get("flag") for a in amb_flags if isinstance(a, dict)],
            "registry_claims": registry.get("claim_count"),
            "drift_status": drift_status,
        },
    }


def _count_l2_eligible(case_dir: Path) -> int:
    from app.l2_l3_corroborative_runtime import classify_l2_folder_screenshot

    n = 0
    for p in case_dir.rglob("*.png"):
        if classify_l2_folder_screenshot(p):
            n += 1
    return n


def profile_rt_noise(result: Dict[str, Any]) -> str:
    rt = (result.get("profile") or {}).get("runtime_evidence") or {}
    flags = rt.get("video_noise_flags") or []
    return " ".join(
        f.get("flag", "") for f in flags if isinstance(f, dict)
    )


def run_corpus(*, limit: Optional[int] = None) -> Dict[str, Any]:
    if not EXPECTED_PATH.exists():
        from app.calibration.runtime_evidence_corpus.generate_corpus import generate_corpus

        generate_corpus(count=80)

    manifest = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    cases_out: List[Dict[str, Any]] = []
    for entry in manifest.get("cases") or []:
        if limit is not None and len(cases_out) >= limit:
            break
        cid = entry.get("case_id") or ""
        case_dir = CORPUS_ROOT / "cases" / cid
        if not case_dir.is_dir():
            cases_out.append({
                "case_id": cid,
                "error": f"missing {case_dir}",
                "all_passed": False,
            })
            continue
        try:
            result = _run_single_case(case_dir)
            cases_out.append(_evaluate_case(entry, result, case_dir))
        except Exception as exc:
            cases_out.append({
                "case_id": cid,
                "error": str(exc),
                "all_passed": False,
            })

    total = len(cases_out)
    passed_all = sum(1 for c in cases_out if c.get("all_passed"))
    report = {
        "corpus_id": manifest.get("corpus_id"),
        "freeze": manifest.get("freeze"),
        "mode": "governance_invariants_only_not_accuracy",
        "cases_run": total,
        "cases_all_passed": passed_all,
        "pass_rate": round(passed_all / total, 3) if total else 0.0,
        "cases": cases_out,
        "summary_ar": (
            f"اختبار governability: {passed_all}/{total} cases passed invariants. "
            "presence ≠ authority — contradictions must remain visible."
        ),
    }
    LAST_RUN_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    report = run_corpus(limit=args.limit)
    print(json.dumps({
        "cases_run": report["cases_run"],
        "cases_all_passed": report["cases_all_passed"],
        "pass_rate": report["pass_rate"],
        "output": str(LAST_RUN_PATH),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
