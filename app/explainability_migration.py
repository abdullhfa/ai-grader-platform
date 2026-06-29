"""
Non-destructive Explainability Migration Layer.

Adds governance intent, missing-evidence diagnostics, and extraction coverage
to existing grading snapshots WITHOUT altering grades, criteria, or adjudication.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.academic_explainability import attach_academic_explainability

EXPLAINABILITY_LAYER_VERSION = "v2"
EXPLAINABILITY_SCHEMA = "2.0"
REVISION_TYPE_BACKFILL = "explainability_backfill"

DISCLAIMER_EN = (
    "Explainability layer added post-assessment. No academic decision was altered."
)
DISCLAIMER_AR = (
    "أُضيفت طبقة الشفافية والتشخيص بعد التقييم — لم يُغيّر أي قرار أكademي** "
    "(الدرجة، المعايير، التحكيم)."
)

# Snapshot keys that must remain byte-identical after backfill (JSON-normalized).
_PROTECTED_TOP_LEVEL_KEYS = frozenset(
    {
        "total_score",
        "max_score",
        "percentage",
        "grade_level",
        "criteria_results",
        "overall_feedback",
        "strengths",
        "improvements",
        "ai_likelihood",
        "ai_detection_info",
        "plagiarism_info",
        "runtime_criterion_support",
        "l5_human_playtest",
        "governance_drift",
        "adjudication",
        "human_adjudication",
        "grading_hash",
        "content_fingerprint",
    }
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _active_policy_version() -> str:
    try:
        from app.governance_freeze_registry import get_active_freeze_id

        return get_active_freeze_id()
    except Exception:
        return "GOVERNANCE_FREEZE_v1"


def _previous_snapshot_hash(snapshot: Dict[str, Any]) -> Optional[str]:
    history = snapshot.get("explainability_revision_history")
    if isinstance(history, list) and history:
        last = history[-1]
        if isinstance(last, dict) and last.get("snapshot_hash"):
            return str(last["snapshot_hash"])
    rev = snapshot.get("explainability_revision") or {}
    if isinstance(rev, dict) and rev.get("snapshot_hash"):
        return str(rev["snapshot_hash"])
    return None


def compute_revision_snapshot_hash(
    revision_meta: Dict[str, Any],
    explainability_layer: Dict[str, Any],
    protected_digest: str,
) -> str:
    """Hashable audit anchor — links explainability to protected academic digest."""
    payload = {
        "protected_digest": protected_digest,
        "explainability_layer": explainability_layer,
        "revision_meta": {
            k: v
            for k, v in revision_meta.items()
            if k not in ("snapshot_hash", "previous_snapshot_hash")
        },
    }
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _protected_digest(snapshot: Dict[str, Any]) -> str:
    """Fingerprint of academic decision fields — must not change on backfill."""
    return academic_decision_digest_from_snapshot(snapshot)


def _normalize_criteria_for_digest(crit: Any) -> List[Dict[str, Any]]:
    if not isinstance(crit, list):
        return []
    rows = [
        {
            "criteria_level": c.get("criteria_level"),
            "achieved": c.get("achieved"),
            "score": c.get("score"),
            "achievement_authority": c.get("achievement_authority"),
        }
        for c in crit
        if isinstance(c, dict)
    ]
    return sorted(rows, key=lambda r: str(r.get("criteria_level") or ""))


def compute_academic_decision_digest(
    *,
    grade_level: Any = None,
    total_score: Any = None,
    max_score: Any = None,
    percentage: Any = None,
    criteria_results: Any = None,
    decision_provenance: Any = None,
    evidence_fingerprint: Any = None,
) -> str:
    """Canonical digest for replay verification — decision + rule bundle + evidence."""
    protected: Dict[str, Any] = {}
    if grade_level is not None:
        protected["grade_level"] = grade_level
    if total_score is not None:
        protected["total_score"] = total_score
    if max_score is not None:
        protected["max_score"] = max_score
    if percentage is not None:
        protected["percentage"] = percentage
    norm = _normalize_criteria_for_digest(criteria_results)
    if norm:
        protected["criteria_results"] = norm
    if isinstance(decision_provenance, dict) and decision_provenance.get("bundle_hash"):
        protected["decision_provenance"] = {
            k: decision_provenance.get(k)
            for k in (
                "rule_version",
                "authority_version",
                "engine_version",
                "governance_freeze",
                "execution_mode",
                "bundle_hash",
                "evidence_hash",
            )
        }
    if isinstance(evidence_fingerprint, dict) and evidence_fingerprint.get("evidence_hash"):
        protected["evidence_fingerprint"] = {
            "version": evidence_fingerprint.get("version"),
            "evidence_hash": evidence_fingerprint.get("evidence_hash"),
        }
    return hashlib.sha256(_stable_json(protected).encode("utf-8")).hexdigest()


def academic_decision_digest_from_snapshot(snapshot: Dict[str, Any]) -> str:
    from app.evidence_fingerprint import fingerprint_from_payload
    from app.rule_bundle import provenance_from_payload

    prov = provenance_from_payload(snapshot)
    fp = fingerprint_from_payload(snapshot)
    return compute_academic_decision_digest(
        grade_level=snapshot.get("grade_level"),
        total_score=snapshot.get("total_score"),
        max_score=snapshot.get("max_score"),
        percentage=snapshot.get("percentage"),
        criteria_results=snapshot.get("criteria_results"),
        decision_provenance=prov,
        evidence_fingerprint=fp,
    )


def _protected_digest_legacy_full(snapshot: Dict[str, Any]) -> str:
    """Full protected fingerprint including non-replay metadata keys."""
    protected = {k: snapshot.get(k) for k in _PROTECTED_TOP_LEVEL_KEYS if k in snapshot}
    crit = protected.get("criteria_results")
    if isinstance(crit, list):
        protected["criteria_results"] = _normalize_criteria_for_digest(crit)
    return hashlib.sha256(_stable_json(protected).encode("utf-8")).hexdigest()


def _protected_digest_full(snapshot: Dict[str, Any]) -> str:
    return _protected_digest_legacy_full(snapshot)


# Backward-compatible alias used by backfill reports
def protected_digest_includes_metadata(snapshot: Dict[str, Any]) -> str:
    return _protected_digest_legacy_full(snapshot)


def _submission_paths_from_snapshot(snapshot: Dict[str, Any], submission_file_path: str = "") -> List[str]:
    paths: List[str] = []
    seen: set[str] = set()

    def _add(p: Optional[str]) -> None:
        if not p:
            return
        ps = p.strip()
        if ps and ps not in seen:
            seen.add(ps)
            paths.append(ps)

    _add(snapshot.get("file_path"))
    _add(submission_file_path)
    if submission_file_path:
        try:
            parent = Path(submission_file_path).parent
            if parent.is_dir():
                _add(str(parent))
        except OSError:
            pass
    inv = snapshot.get("artifact_inventory") or {}
    for block_key in ("documentation", "source_code", "executable_artifacts"):
        block = inv.get(block_key) or {}
        for entry in block.get("files") or []:
            if isinstance(entry, dict):
                _add(entry.get("path"))

    return paths


def build_explainability_revision_meta(
    *,
    source: str = "explainability_migration_backfill",
    trigger: str = "admin_backfill",
    generated_by: str = "system",
    previous_snapshot_hash: Optional[str] = None,
    protected_digest: Optional[str] = None,
    explainability_layer: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "version": EXPLAINABILITY_LAYER_VERSION,
        "explainability_schema": EXPLAINABILITY_SCHEMA,
        "policy_version": _active_policy_version(),
        "generated_by": generated_by,
        "trigger": trigger,
        "revision_type": REVISION_TYPE_BACKFILL,
        "generated_at": _utc_now_iso(),
        "non_destructive": True,
        "disclaimer_en": DISCLAIMER_EN,
        "disclaimer_ar": DISCLAIMER_AR,
        "source": source,
    }
    if protected_digest:
        meta["protected_digest"] = protected_digest
    if previous_snapshot_hash:
        meta["previous_snapshot_hash"] = previous_snapshot_hash
    if explainability_layer is not None and protected_digest:
        meta["snapshot_hash"] = compute_revision_snapshot_hash(
            meta, explainability_layer, protected_digest
        )
    return meta


def _append_revision_history(snapshot: Dict[str, Any], revision: Dict[str, Any]) -> None:
    history = snapshot.get("explainability_revision_history")
    if not isinstance(history, list):
        history = []
    history.append(copy.deepcopy(revision))
    snapshot["explainability_revision_history"] = history


def explainability_already_current(snapshot: Dict[str, Any]) -> bool:
    rev = snapshot.get("explainability_revision") or {}
    if rev.get("version") != EXPLAINABILITY_LAYER_VERSION:
        return False
    layer = snapshot.get("explainability_layer") or {}
    has_lineage = bool(
        (layer.get("evidence_lineage") or snapshot.get("evidence_lineage") or {}).get("criteria")
    )
    return bool(
        layer.get("governance_intent")
        and layer.get("missing_evidence_diagnostics")
        and has_lineage
    )


def refresh_runtime_observation_in_inventory(
    inventory: Dict[str, Any],
    *,
    submission_paths: List[str],
    student_name: str = "",
    submission_id: Optional[int] = None,
    batch_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Re-run L4 sandbox observation and merge results into an artifact inventory."""
    from app.governance_freeze_registry import is_l4_sandbox_permitted

    if not submission_paths or not is_l4_sandbox_permitted():
        return inventory

    try:
        from app.evidence_completeness_gate import expand_submission_paths

        expanded = expand_submission_paths(
            list(submission_paths),
            primary_path=submission_paths[0] if submission_paths else "",
            student_name=student_name or "",
        )
    except Exception:
        expanded = list(submission_paths)

    try:
        from app.runtime.sandbox_engine import run_sandbox_observation
        from app.runtime.validation_engine import validate_runtime_observation

        obs = run_sandbox_observation(
            expanded,
            submission_id=submission_id,
            batch_id=batch_id,
            student_name=student_name or "",
            enable_smoke_test=True,
        )
        obs["runtime_validation"] = validate_runtime_observation(obs)
        inventory["runtime_observation_report"] = obs
        inventory["runtime_validation"] = obs.get("runtime_validation")

        exe_block = inventory.setdefault("executable_artifacts", {})
        if not isinstance(exe_block, dict):
            exe_block = {}
            inventory["executable_artifacts"] = exe_block
        exe_block["runtime_verified"] = bool(obs.get("runtime_verified"))
        exe_block["runtime_observed"] = bool(obs.get("runtime_observed"))
        if obs.get("status") in ("completed", "failed", "crashed", "timeout"):
            exe_block["runtime_observation"] = str(obs.get("status") or "completed")
            if obs.get("runtime_observed"):
                exe_block["status"] = "observed_runtime_advisory"

        try:
            from app.runtime_evidence_package import _collect_runtime_screenshots

            shots = _collect_runtime_screenshots(obs, inventory)
        except Exception:
            shots = obs.get("runtime_screenshots") or []
        if shots:
            rt_art = inventory.setdefault("runtime_artifacts", {})
            if isinstance(rt_art, dict):
                rt_art["runtime_screenshots"] = shots
                rt_art["runtime_screenshot_count"] = sum(
                    1
                    for s in shots
                    if isinstance(s, dict) and s.get("status") == "captured"
                )
                rt_art["runtime_observed"] = bool(obs.get("runtime_observed"))
                inventory["runtime_artifacts"] = rt_art

        if obs.get("runtime_observed"):
            inventory["runtime_verification"] = {
                "status": "observed_advisory",
                "mode": obs.get("observation_mode"),
                "verified": bool(obs.get("runtime_verified")),
                "human_authority_required": True,
            }
    except Exception as exc:
        inventory["runtime_observation_refresh_error"] = str(exc)

    return inventory


def _enrich_slim_inventory_for_ui(inv: Dict[str, Any], snapshot: Dict[str, Any]) -> None:
    """Restore minimal evidence flags stripped from BASIC snapshots (UI diagnostics only)."""
    from app.grading_mode_policy import enrich_artifact_inventory_from_snapshot_meta

    enrich_artifact_inventory_from_snapshot_meta(inv, snapshot)


def compute_explainability_layer(
    snapshot: Dict[str, Any],
    *,
    submission_paths: Optional[List[str]] = None,
    project_profile: Optional[Dict[str, Any]] = None,
    rerun_runtime: bool = False,
    student_name: str = "",
    submission_id: Optional[int] = None,
    batch_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Build explainability blocks from existing snapshot inventory (read-only inputs)."""
    inv = copy.deepcopy(snapshot.get("artifact_inventory") or {})
    _enrich_slim_inventory_for_ui(inv, snapshot)
    paths = submission_paths or _submission_paths_from_snapshot(snapshot)
    profile = project_profile or snapshot.get("project_profile") or {}
    if rerun_runtime and paths:
        refresh_runtime_observation_in_inventory(
            inv,
            submission_paths=paths,
            student_name=student_name,
            submission_id=submission_id,
            batch_id=batch_id,
        )
        try:
            from app.artifact_inventory import (
                SOURCE_CODE_EXTENSIONS,
                _augment_godot_export_source_files,
                _existing_files,
                _resolve_inventory_paths,
            )

            primary = next(
                (p for p in paths if p.lower().endswith((".docx", ".doc", ".pdf", ".odt"))),
                paths[0],
            )
            expanded = _resolve_inventory_paths(
                paths,
                main_document_path=primary,
                student_name=student_name,
            )
            files = _existing_files(expanded)
            src_files: List[Dict[str, Any]] = []
            for fp in files:
                ext = fp.suffix.lower()
                if ext in SOURCE_CODE_EXTENSIONS:
                    src_files.append(
                        {
                            "name": fp.name,
                            "path": str(fp),
                            "ext": ext,
                            "size_bytes": fp.stat().st_size,
                        }
                    )
            src_files = _augment_godot_export_source_files(src_files, files)
            inv["source_code"] = {
                "status": "analyzed" if src_files else "not_detected",
                "files": src_files,
            }
        except Exception as exc:
            inv["source_code_refresh_error"] = str(exc)
    # Avoid rglob over full student trees on every UI read — use inventory file lists only.
    attach_academic_explainability(inv, submission_paths=None, project_profile=profile, grading_mode=snapshot.get("grading_mode"))
    from app.evidence_lineage import attach_evidence_lineage_to_snapshot

    partial = {
        "artifact_inventory": inv,
        "criteria_results": snapshot.get("criteria_results") or [],
        "runtime_criterion_support": snapshot.get("runtime_criterion_support")
        or inv.get("runtime_criterion_support"),
        "explainability_layer": {
            "governance_intent": inv.get("governance_intent") or {},
        },
    }
    attach_evidence_lineage_to_snapshot(partial)
    lineage = partial.get("evidence_lineage") or {}
    return {
        "governance_intent": inv.get("governance_intent") or {},
        "missing_evidence_diagnostics": inv.get("missing_evidence_diagnostics") or {},
        "extraction_coverage": inv.get("extraction_coverage") or {},
        "evidence_lineage": lineage,
        "inventory": inv,
    }


def apply_explainability_backfill(
    snapshot: Dict[str, Any],
    *,
    submission_paths: Optional[List[str]] = None,
    project_profile: Optional[Dict[str, Any]] = None,
    force: bool = False,
    source: str = "explainability_migration_backfill",
    trigger: str = "admin_backfill",
    generated_by: str = "system",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Return (updated_snapshot, report).
    Raises ValueError if protected academic fields would change.
    """
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be a dict")

    report: Dict[str, Any] = {
        "applied": False,
        "skipped": False,
        "reason": "",
        "protected_digest_before": _protected_digest(snapshot),
    }

    if explainability_already_current(snapshot) and not force:
        report["skipped"] = True
        report["reason"] = "already_at_version"
        return snapshot, report

    before_digest = report["protected_digest_before"]
    updated = copy.deepcopy(snapshot)

    profile = project_profile if isinstance(project_profile, dict) else {}
    rerun_runtime = bool(profile.get("rerun_runtime"))
    layer = compute_explainability_layer(
        updated,
        submission_paths=submission_paths,
        project_profile=project_profile,
        rerun_runtime=rerun_runtime,
        student_name=str(updated.get("student_name") or ""),
        submission_id=updated.get("submission_id"),
        batch_id=updated.get("batch_id"),
    )

    layer_public = {k: v for k, v in layer.items() if k != "inventory"}
    updated["explainability_layer"] = layer_public
    inv = updated.setdefault("artifact_inventory", {})
    if isinstance(inv, dict) and isinstance(layer.get("inventory"), dict):
        refreshed_inv = layer["inventory"]
        for key in (
            "governance_intent",
            "missing_evidence_diagnostics",
            "extraction_coverage",
            "runtime_observation_report",
            "runtime_verification",
            "executable_artifacts",
            "runtime_artifacts",
            "source_code",
        ):
            if key in refreshed_inv:
                inv[key] = refreshed_inv[key]
    revision = build_explainability_revision_meta(
        source=source,
        trigger=trigger,
        generated_by=generated_by,
        previous_snapshot_hash=_previous_snapshot_hash(snapshot),
        protected_digest=before_digest,
        explainability_layer=layer_public,
    )
    updated["explainability_revision"] = revision
    _append_revision_history(updated, revision)

    # Mirror into artifact_inventory for report/UI consumers (additive keys only).
    inv = updated.setdefault("artifact_inventory", {})
    if not isinstance(inv, dict):
        inv = {}
        updated["artifact_inventory"] = inv
    inv["governance_intent"] = layer["governance_intent"]
    inv["missing_evidence_diagnostics"] = layer["missing_evidence_diagnostics"]
    inv["extraction_coverage"] = layer["extraction_coverage"]
    inv["explainability_revision"] = updated["explainability_revision"]
    if layer.get("evidence_lineage"):
        updated["evidence_lineage"] = layer["evidence_lineage"]
        inv["evidence_lineage"] = layer["evidence_lineage"]

    try:
        from app.institutional_grade_resolution import attach_institutional_grade_resolution

        attach_institutional_grade_resolution(updated, artifact_inventory=inv)
    except Exception:
        pass

    after_digest = _protected_digest(updated)
    report["protected_digest_after"] = after_digest

    if before_digest != after_digest:
        raise ValueError(
            "Explainability backfill would alter protected academic fields — aborted."
        )

    report["applied"] = True
    report["reason"] = "backfill_applied"
    report["snapshot_hash"] = revision.get("snapshot_hash")
    report["previous_snapshot_hash"] = revision.get("previous_snapshot_hash")
    return updated, report


def _institutional_resolution_for_ui(snapshot: Dict[str, Any], inv: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    inst = snapshot.get("institutional_resolution")
    if isinstance(inst, dict) and inst.get("version"):
        return inst
    try:
        from app.institutional_grade_resolution import resolve_institutional_classification

        obs = inv.get("runtime_observation_report") or {}
        tier = obs.get("confidence_tier")
        return resolve_institutional_classification(
            {
                "grade_level": snapshot.get("grade_level", ""),
                "percentage": snapshot.get("percentage", 0),
                "criteria_results": snapshot.get("criteria_results") or [],
                "artifact_inventory": inv,
            },
            artifact_inventory=inv,
            confidence_tier=tier if isinstance(tier, dict) else None,
        )
    except Exception:
        return None


def refresh_explainability_view_for_ui(
    snapshot: Dict[str, Any],
    *,
    submission_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Recompute governance / diagnostics / institutional resolution from snapshot inventory
    without altering protected academic fields (read-only refresh for UI & Word export).
    """
    paths = submission_paths or _submission_paths_from_snapshot(snapshot)
    layer = compute_explainability_layer(
        snapshot,
        submission_paths=paths,
        project_profile=snapshot.get("project_profile"),
    )
    inv = copy.deepcopy(snapshot.get("artifact_inventory") or {})
    inv["governance_intent"] = layer.get("governance_intent") or {}
    inv["missing_evidence_diagnostics"] = layer.get("missing_evidence_diagnostics") or {}
    inv["extraction_coverage"] = layer.get("extraction_coverage") or {}
    if layer.get("evidence_lineage"):
        inv["evidence_lineage"] = layer["evidence_lineage"]

    wrapper = {
        "grade_level": snapshot.get("grade_level", ""),
        "percentage": snapshot.get("percentage", 0),
        "criteria_results": snapshot.get("criteria_results") or [],
        "artifact_inventory": inv,
    }
    try:
        from app.institutional_grade_resolution import attach_institutional_grade_resolution

        attach_institutional_grade_resolution(wrapper, artifact_inventory=inv)
    except Exception:
        pass
    inst = wrapper.get("institutional_resolution")
    gov = dict(inv.get("governance_intent") or {})
    if isinstance(inst, dict):
        rt = inst.get("runtime_resolution") or {}
        if rt.get("summary_ar"):
            gov["runtime_resolution_ar"] = rt["summary_ar"]
        if inst.get("display_grade_ar"):
            gov["institutional_outcome_ar"] = inst["display_grade_ar"]
        if rt.get("runtime_observed"):
            gov["runtime_execution_ar"] = rt.get("summary_ar", gov.get("runtime_execution_ar", ""))
            gov["not_a_system_failure_ar"] = (
                "تمت ملاحظة runtime — التقييم الاستشاري لا يعادل تحقق المعيار تلقائياً."
            )
    return {
        "governance_intent": gov,
        "missing_evidence_diagnostics": inv.get("missing_evidence_diagnostics"),
        "extraction_coverage": inv.get("extraction_coverage"),
        "evidence_lineage": layer.get("evidence_lineage"),
        "institutional_resolution": inst,
        "runtime_resolution_summary": wrapper.get("runtime_resolution_summary")
        or (inst or {}).get("runtime_resolution"),
    }


def _snapshot_inventory_for_ui(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Merge snapshot top-level evidence fields into inventory for UI diagnostics."""
    inv = copy.deepcopy(snapshot.get("artifact_inventory") or {})
    _enrich_slim_inventory_for_ui(inv, snapshot)
    for key in (
        "criterion_authority",
        "visual_evidence_summary",
        "criteria_results",
        "basic_video_keyframes_meta",
        "content_fingerprint",
        "grading_mode",
        "execution_mode",
    ):
        val = snapshot.get(key)
        if val is not None:
            inv[key] = val
    return inv


def _diagnostics_stale_for_ui(snapshot: Dict[str, Any], diag: Any) -> bool:
    """True when stored checklist rows use retired labels or legacy status text."""
    if not isinstance(diag, dict) or not diag.get("rows"):
        return True
    from app.academic_explainability import (
        _REMOVED_DIAGNOSTIC_REQUIREMENTS_AR,
        _WORD_REPORT_LEGACY_AR,
    )

    for row in diag.get("rows") or []:
        req = str(row.get("requirement_ar") or "")
        if req in _REMOVED_DIAGNOSTIC_REQUIREMENTS_AR or req == _WORD_REPORT_LEGACY_AR:
            return True
        status = str(row.get("status_ar") or "")
        if any(
            token in status
            for token in (
                "جزئي — Authority",
                "موجود:",
                "حلل ",
                "مرسل:",
                "محلل:",
                "إطار/فيديو ×",
            )
        ):
            return True
    if _diagnostics_contradict_fingerprint(snapshot, diag):
        return True
    if _runtime_diag_contradicts_inventory(snapshot, diag):
        return True
    return False


def _runtime_diag_contradicts_inventory(snapshot: Dict[str, Any], diag: Any) -> bool:
    """Stale when UI shows runtime 'verified' but inventory proves no game launch."""
    if not isinstance(diag, dict):
        return False
    inv = _snapshot_inventory_for_ui(snapshot)
    obs = inv.get("runtime_observation_report") or {}
    rv = inv.get("runtime_validation") or obs.get("runtime_validation") or {}
    smoke = (rv.get("functional_smoke") or {}) if isinstance(rv, dict) else {}
    smoke_pass = smoke.get("functional_smoke_pass") is True
    signals = {}
    if obs.get("platform_analyses"):
        signals = (obs["platform_analyses"][0] or {}).get("signals") or {}
    method = str(
        obs.get("observation_mode")
        or obs.get("runtime_method")
        or signals.get("runtime_method")
        or ""
    )
    structure_only = method in (
        "godot_static_analysis",
        "godot_apk_pck_static_scan",
    ) or obs.get("game_launch_attempted") is False
    pairing = signals.get("pck_pairing") or {}
    if pairing.get("error") in ("no_donor_exe_for_pck",):
        structure_only = True
    pck_smoke = signals.get("pck_smoke") or {}
    if pck_smoke.get("error") == "godot_binary_not_configured":
        structure_only = True
    if (
        obs.get("status") in ("completed", "partial")
        and obs.get("runtime_verified") is not True
        and not smoke_pass
    ):
        structure_only = True

    runtime_row = None
    for row in diag.get("rows") or []:
        if str(row.get("requirement_ar") or "") == "التحقق من التشغيل (runtime)":
            runtime_row = row
            break
    if not runtime_row:
        return structure_only
    status_ar = str(runtime_row.get("status_ar") or "")
    if structure_only and (
        runtime_row.get("present")
        or status_ar.startswith("تم التدقيق")
        or "تشغيل آلية" in status_ar
    ):
        return True
    if not smoke_pass and runtime_row.get("present") and "L5" not in status_ar:
        return True
    return False


def _rebuild_diagnostics_for_ui(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    from app.academic_explainability import (
        apply_basic_pro_upgrade_display,
        build_missing_evidence_diagnostics,
    )

    inv = _snapshot_inventory_for_ui(snapshot)
    gm = snapshot.get("grading_mode")
    gm_s = gm if isinstance(gm, str) else None
    diag = build_missing_evidence_diagnostics(inv, grading_mode=gm_s)
    return apply_basic_pro_upgrade_display(diag, inv, grading_mode=gm_s) or diag


def _diagnostics_contradict_fingerprint(snapshot: Dict[str, Any], diag: Any) -> bool:
    """True when stored checklist ignores known Word/screenshot signals in the snapshot."""
    if not isinstance(diag, dict) or not diag.get("rows"):
        return False
    fp = snapshot.get("content_fingerprint") if isinstance(snapshot.get("content_fingerprint"), dict) else {}
    word_count = int(fp.get("word_count") or 0)
    image_count = int(fp.get("image_count") or 0)
    rows = {str(r.get("requirement_ar") or ""): r for r in diag.get("rows") or []}
    word_row = (
        rows.get("تقرير Word/PDF")
        or rows.get("تقرير Word/PDF (GDD/توثيق)")
    )
    shot_row = rows.get("لقطات شاشة") or rows.get("لقطات شاشة للعبة")
    vision_row = rows.get("حالة الأدلة البصرية (Vision)")
    code_row = rows.get("تغطية الكود المصدري")
    inv = snapshot.get("artifact_inventory") or {}
    if word_count > 200 and word_row and not word_row.get("present"):
        return True
    if image_count > 0:
        if shot_row and not shot_row.get("present"):
            return True
        if not shot_row and vision_row and not vision_row.get("present"):
            return True
    if inv.get("has_source_code_artifacts") and code_row and not code_row.get("present"):
        return True
    return False


EXPLAINABILITY_UI_DIAG_VERSION = "runtime_honesty_v3"


def extract_explainability_for_ui(snapshot: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Unified read path: always serve fresh diagnostics text for UI (grades unchanged)."""
    if not snapshot or not isinstance(snapshot, dict):
        return None
    inv = _snapshot_inventory_for_ui(snapshot)
    refreshed: Dict[str, Any] = {}
    try:
        refreshed = refresh_explainability_view_for_ui(snapshot)
    except Exception as exc:
        print(f"⚠️ [EXPLAINABILITY] refresh failed: {exc}")
        try:
            layer = compute_explainability_layer(
                snapshot,
                submission_paths=_submission_paths_from_snapshot(snapshot),
                project_profile=snapshot.get("project_profile"),
            )
            refreshed = {
                "governance_intent": layer.get("governance_intent") or {},
                "missing_evidence_diagnostics": layer.get("missing_evidence_diagnostics") or {},
                "extraction_coverage": layer.get("extraction_coverage") or {},
                "evidence_lineage": layer.get("evidence_lineage") or {},
                "institutional_resolution": None,
                "runtime_resolution_summary": None,
            }
        except Exception as inner:
            print(f"⚠️ [EXPLAINABILITY] fallback compute failed: {inner}")
            refreshed = {}
    layer = snapshot.get("explainability_layer") or {}
    gov = refreshed.get("governance_intent") or layer.get("governance_intent") or inv.get("governance_intent")
    # Always rebuild checklist from inventory so stale L4 "تم التدقيق" never survives in UI.
    diag = _rebuild_diagnostics_for_ui(snapshot)
    if isinstance(diag, dict):
        diag = dict(diag)
        diag["ui_diag_version"] = EXPLAINABILITY_UI_DIAG_VERSION
    cov = refreshed.get("extraction_coverage") or layer.get("extraction_coverage") or inv.get("extraction_coverage")
    rev = snapshot.get("explainability_revision") or inv.get("explainability_revision")
    lineage = (
        refreshed.get("evidence_lineage")
        or layer.get("evidence_lineage")
        or snapshot.get("evidence_lineage")
        or inv.get("evidence_lineage")
    )
    inst = refreshed.get("institutional_resolution") or _institutional_resolution_for_ui(snapshot, inv)
    if not gov and not diag and not inst:
        return None
    history = snapshot.get("explainability_revision_history")
    cov_rows = snapshot.get("evidence_coverage_by_criterion") or inv.get(
        "evidence_coverage_by_criterion"
    )
    miss_report = snapshot.get("missing_evidence_report") or inv.get("missing_evidence_report")
    req_checklist = snapshot.get("requirement_checklist") or inv.get("requirement_checklist")
    rt_pkg = snapshot.get("runtime_evidence_package") or inv.get("runtime_evidence_package")
    if not rt_pkg and inv.get("runtime_observation_report"):
        try:
            from app.runtime_evidence_package import attach_runtime_evidence_package

            _tmp_rt: Dict[str, Any] = {"artifact_inventory": inv}
            attach_runtime_evidence_package(
                _tmp_rt,
                artifact_inventory=inv,
                requirement_checklist=req_checklist,
                submission_paths=_submission_paths_from_snapshot(snapshot),
                student_text=str(snapshot.get("student_text") or "")[:50000],
            )
            rt_pkg = _tmp_rt.get("runtime_evidence_package")
            req_checklist = _tmp_rt.get("requirement_checklist") or req_checklist
        except Exception:
            pass
    if not cov_rows:
        try:
            from app.evidence_coverage_score import attach_evidence_coverage_package

            _tmp = {"artifact_inventory": inv, "criteria_results": snapshot.get("criteria_results") or []}
            attach_evidence_coverage_package(
                _tmp,
                artifact_inventory=inv,
                student_text=str(snapshot.get("student_text") or "")[:50000],
                word_only_text=str(
                    snapshot.get("plagiarism_text") or snapshot.get("student_text") or ""
                )[:50000],
                submission_paths=_submission_paths_from_snapshot(snapshot),
            )
            cov_rows = _tmp.get("evidence_coverage_by_criterion")
            miss_report = _tmp.get("missing_evidence_report")
        except Exception:
            pass

    out: Dict[str, Any] = {
        "governance_intent": gov,
        "missing_evidence_diagnostics": diag,
        "extraction_coverage": cov,
        "explainability_revision": rev,
        "evidence_lineage": lineage,
        "institutional_resolution": inst,
        "evidence_coverage_by_criterion": cov_rows,
        "missing_evidence_report": miss_report,
        "requirement_checklist": req_checklist,
        "runtime_evidence_package": rt_pkg,
        "runtime_resolution_summary": snapshot.get("runtime_resolution_summary")
        or (inst or {}).get("runtime_resolution"),
        "visual_evidence_summary": (
            snapshot.get("visual_evidence_summary")
            or inv.get("visual_evidence_summary")
        ),
        "criterion_authority": (
            snapshot.get("criterion_authority")
            or inv.get("criterion_authority")
        ),
    }
    if isinstance(history, list) and history:
        out["explainability_revision_history"] = history
    return out


def _integrity_risk_from_preview(*, has_snapshot: bool, valid_json: bool, dry_error: Optional[str]) -> str:
    if not has_snapshot:
        return "medium"
    if not valid_json:
        return "medium"
    if dry_error:
        return "high"
    return "low"


def preview_submission_backfill(
    submission,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """Dry-run impact row for one submission — no DB writes."""
    sid = getattr(submission, "id", None)
    raw = getattr(submission, "grading_snapshot_json", None)
    base: Dict[str, Any] = {
        "submission_id": sid,
        "student_name": getattr(submission, "student_name", "") or "",
        "has_snapshot": bool(raw),
        "valid_json": False,
        "explainability_missing": False,
        "would_apply": False,
        "would_skip": False,
        "skip_reason": "",
        "integrity_risk": "medium",
        "protected_digest": None,
    }
    if not raw:
        base["explainability_missing"] = True
        base["would_skip"] = True
        base["skip_reason"] = "no_snapshot"
        return base

    try:
        snap = json.loads(str(raw))
        base["valid_json"] = True
    except (json.JSONDecodeError, TypeError):
        base["would_skip"] = True
        base["skip_reason"] = "invalid_json"
        return base

    base["explainability_missing"] = not explainability_already_current(snap)
    base["protected_digest"] = _protected_digest(snap)

    if explainability_already_current(snap) and not force:
        base["would_skip"] = True
        base["skip_reason"] = "already_at_version"
        base["integrity_risk"] = "low"
        return base

    paths = _submission_paths_from_snapshot(
        snap, str(getattr(submission, "submission_file_path", "") or "")
    )
    dry_error: Optional[str] = None
    try:
        _, report = apply_explainability_backfill(
            snap,
            submission_paths=paths,
            project_profile=snap.get("project_profile"),
            force=force,
            trigger="admin_backfill_preview",
            generated_by="system",
        )
        base["would_apply"] = bool(report.get("applied"))
        base["would_skip"] = bool(report.get("skipped"))
        base["skip_reason"] = str(report.get("reason") or "")
    except ValueError as exc:
        dry_error = str(exc)
        base["would_skip"] = True
        base["skip_reason"] = "integrity_check_failed"

    base["integrity_risk"] = _integrity_risk_from_preview(
        has_snapshot=True,
        valid_json=True,
        dry_error=dry_error,
    )
    return base


def preview_backfill_batch(db, batch_id: int, *, force: bool = False) -> Dict[str, Any]:
    """Impact table before batch backfill — submissions / missing / integrity risk."""
    from app.models import Submission, SubmissionStatus

    subs = (
        db.query(Submission)
        .filter(Submission.batch_id == batch_id, Submission.status == SubmissionStatus.COMPLETED)
        .all()
    )
    rows = [preview_submission_backfill(s, force=force) for s in subs]
    missing = sum(1 for r in rows if r.get("explainability_missing"))
    would_apply = sum(1 for r in rows if r.get("would_apply"))
    risk_counts = {"low": 0, "medium": 0, "high": 0}
    for r in rows:
        level = str(r.get("integrity_risk") or "medium")
        if level not in risk_counts:
            level = "medium"
        risk_counts[level] += 1

    if risk_counts["high"] > 0:
        overall_risk = "high"
    elif risk_counts["medium"] > 0:
        overall_risk = "medium"
    else:
        overall_risk = "low"

    return {
        "batch_id": batch_id,
        "submissions": len(rows),
        "explainability_missing": missing,
        "would_apply": would_apply,
        "would_skip": len(rows) - would_apply,
        "integrity_risk": overall_risk,
        "integrity_risk_breakdown": risk_counts,
        "force": force,
        "rows": rows,
    }


def backfill_submission_record(
    submission,
    *,
    db=None,
    dry_run: bool = False,
    force: bool = False,
    rerun_runtime: bool = False,
    generated_by: str = "system",
    trigger: str = "admin_backfill",
) -> Dict[str, Any]:
    """Apply explainability backfill to one ORM Submission row."""
    raw = getattr(submission, "grading_snapshot_json", None)
    if not raw:
        return {"submission_id": getattr(submission, "id", None), "skipped": True, "reason": "no_snapshot"}

    try:
        snap = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return {"submission_id": getattr(submission, "id", None), "skipped": True, "reason": "invalid_json"}

    paths = _submission_paths_from_snapshot(
        snap, str(getattr(submission, "submission_file_path", "") or "")
    )
    profile = dict(snap.get("project_profile") or {})
    if rerun_runtime:
        profile["rerun_runtime"] = True
    snap["student_name"] = getattr(submission, "student_name", "") or snap.get("student_name")
    snap["submission_id"] = getattr(submission, "id", None)
    snap["batch_id"] = getattr(submission, "batch_id", None)
    try:
        updated, report = apply_explainability_backfill(
            snap,
            submission_paths=paths,
            project_profile=profile,
            force=force,
            generated_by=generated_by,
            trigger=trigger,
        )
    except ValueError as exc:
        return {
            "submission_id": getattr(submission, "id", None),
            "skipped": True,
            "reason": "integrity_check_failed",
            "error": str(exc),
        }

    report["submission_id"] = getattr(submission, "id", None)
    report["student_name"] = getattr(submission, "student_name", "")

    if report.get("applied") and not dry_run:
        submission.grading_snapshot_json = json.dumps(updated, ensure_ascii=False)  # type: ignore[assignment]
        inst = updated.get("institutional_resolution") or {}
        inst_disp = updated.get("institutional_grade_display") or inst.get("display_grade_ar")
        if inst_disp and db is not None:
            try:
                from app.models import GradingSummary

                summary = (
                    db.query(GradingSummary)
                    .filter(GradingSummary.submission_id == getattr(submission, "id", None))
                    .first()
                )
                if summary and str(summary.grade_level or "").strip().upper().startswith("U"):
                    summary.grade_level = str(inst_disp)  # type: ignore[assignment]
            except Exception:
                pass

    if report.get("applied") and not dry_run and updated.get("explainability_revision"):
        try:
            from app.academic_event_replay import append_explainability_revision_event

            append_explainability_revision_event(updated, updated["explainability_revision"])
            submission.grading_snapshot_json = json.dumps(updated, ensure_ascii=False)  # type: ignore[assignment]
        except Exception:
            pass

    return report


def backfill_batch_submissions(
    db,
    batch_id: int,
    *,
    dry_run: bool = False,
    force: bool = False,
    generated_by: str = "system",
    trigger: str = "admin_backfill",
) -> Dict[str, Any]:
    """Backfill all completed submissions in a batch."""
    from app.models import Submission, SubmissionStatus

    subs = (
        db.query(Submission)
        .filter(Submission.batch_id == batch_id, Submission.status == SubmissionStatus.COMPLETED)
        .all()
    )
    results = [
        backfill_submission_record(
            s,
            dry_run=dry_run,
            force=force,
            generated_by=generated_by,
            trigger=trigger,
        )
        for s in subs
    ]
    applied = sum(1 for r in results if r.get("applied"))
    skipped = sum(1 for r in results if r.get("skipped"))
    return {
        "batch_id": batch_id,
        "total": len(results),
        "applied": applied,
        "skipped": skipped,
        "dry_run": dry_run,
        "results": results,
    }
