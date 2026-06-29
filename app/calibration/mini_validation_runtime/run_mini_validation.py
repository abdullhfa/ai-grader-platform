"""
Run 5 synthetic mini cases against build_project_profile + evidence_layer.

Usage (from repo root):
  python -m app.calibration.mini_validation_runtime.run_mini_validation

Fills actual_behavior with a compact JSON snapshot; leave observed_friction /
unexpected_result for humans after review (or edit the merged file by hand).
Does not assert correctness — observation only.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _collect_file_paths(case_dir: Path) -> List[str]:
    out: List[str] = []
    for p in sorted(case_dir.rglob("*")):
        if p.is_file():
            out.append(str(p.resolve()))
    return out


def _compact_snapshot(profile: Dict[str, Any], evidence_layer: Dict[str, Any]) -> Dict[str, Any]:
    rc = evidence_layer.get("runtime_corroboration") or {}
    by_sys = rc.get("by_system") or {}
    slim_systems = {
        k: {
            "corroboration_strength": v.get("corroboration_strength"),
            "weighted_corroboration_score": v.get("weighted_corroboration_score"),
            "modality_diversity_score": v.get("modality_diversity_score"),
            "corroboration_modalities": v.get("corroboration_modalities"),
            "runtime_corroborated": v.get("runtime_corroborated"),
            "source_confidence_tier": v.get("source_confidence_tier"),
            "corroboration_reasoning": v.get("corroboration_reasoning"),
            "corroboration_noise_flags": v.get("corroboration_noise_flags"),
            "modality_confidence_tiers": v.get("modality_confidence_tiers"),
        }
        for k, v in by_sys.items()
        if isinstance(v, dict)
    }
    return {
        "engines_detected": profile.get("engines_detected"),
        "systems_detected": profile.get("systems_detected"),
        "runtime_evidence": {
            "screenshot_count": len((profile.get("runtime_evidence") or {}).get("screenshot_candidates") or []),
            "log_count": len((profile.get("runtime_evidence") or {}).get("log_files") or []),
        },
        "corroboration": {
            "by_system": slim_systems,
            "missing_runtime_corroboration_flags": rc.get("missing_runtime_corroboration_flags") or [],
            "corroboration_conflicts": rc.get("corroboration_conflicts") or [],
            "aggregate_log_signals": rc.get("aggregate_log_signals") or {},
            "evidence_weights": rc.get("evidence_weights") or {},
            "modality_confidence_tier_reference": rc.get("modality_confidence_tier_reference") or {},
        },
    }


def run_all() -> Dict[str, Any]:
    root = Path(__file__).resolve().parent
    expected_path = root / "expected_cases.json"
    template = json.loads(expected_path.read_text(encoding="utf-8"))

    from app.project_intelligence.evidence_schema import build_evidence_layer_from_profile
    from app.project_intelligence.project_profile import build_project_profile

    cases_out: List[Dict[str, Any]] = []
    for entry in template.get("cases") or []:
        cid = entry.get("case_id") or ""
        case_dir = root / "cases" / cid
        if not case_dir.is_dir():
            cases_out.append({**entry, "actual_behavior": json.dumps({"error": f"missing {case_dir}"})})
            continue
        paths = _collect_file_paths(case_dir)
        profile = build_project_profile(paths)
        evidence_layer = build_evidence_layer_from_profile(profile)
        snap = _compact_snapshot(profile, evidence_layer)
        merged = {
            **entry,
            "actual_behavior": json.dumps(snap, ensure_ascii=False, indent=2),
        }
        cases_out.append(merged)

    return {
        "run_purpose": template.get("run_purpose", ""),
        "cases": cases_out,
        "note": "Fill observed_friction and unexpected_result after manual review; do not auto-tune thresholds from a single run.",
    }


def main() -> None:
    out = run_all()
    root = Path(__file__).resolve().parent
    out_path = root / "mini_validation_last_run.json"
    # Preserve human fields from previous run if present (merge by case_id)
    if out_path.is_file():
        prev = json.loads(out_path.read_text(encoding="utf-8"))
        prev_by_id = {c.get("case_id"): c for c in (prev.get("cases") or [])}
        for c in out["cases"]:
            pid = c.get("case_id")
            old = prev_by_id.get(pid) if isinstance(prev_by_id, dict) else None
            if isinstance(old, dict):
                for key in ("observed_friction", "unexpected_result", "corroboration_observation_notes"):
                    if old.get(key):
                        c[key] = old[key]
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
