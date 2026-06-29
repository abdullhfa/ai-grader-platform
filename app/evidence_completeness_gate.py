"""
Evidence Completeness Pre-Gate — deterministic required-artifact check before AI grading.

Non-destructive: records gaps in snapshot; does not block grading unless strict mode.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

GATE_VERSION = "evidence_completeness_v2"

_DOC_EXT = frozenset({".doc", ".docx", ".pdf", ".rtf", ".odt"})
_CODE_EXT = frozenset(
    {".cs", ".py", ".java", ".cpp", ".c", ".js", ".ts", ".gd", ".gml", ".html", ".yyp", ".yy"}
)
_EXE_EXT = frozenset({".exe", ".apk", ".pck", ".app", ".sb3", ".sb2", ".win"})
# Scratch playable project + GameMaker exported build are runnable deliverables —
# sourced from the shared single-source registry to avoid drift across paths.
from app.game_engine_signatures import (  # noqa: E402
    RUNNABLE_GAME_EXTENSIONS as _RUNNABLE_GAME_EXT,
    RUNNABLE_GAME_FILENAMES as _RUNNABLE_GAME_FILENAMES,
)
_SKIP_DIRS = frozenset(
    {
        "monobleedingedge",
        "library",
        "temp",
        "obj",
        "bin",
        "node_modules",
        ".godot",
        ".import",
        "embedruntime",
    }
)

_GDD_PATTERN = re.compile(
    r"gdd|game\s+design|وثيق[ةه]\s+(?:ب)?تصميم|تصميم\s+(?:إلكترونية\s+)?اللعبة",
    re.IGNORECASE,
)
_PEER_PATTERN = re.compile(
    r"peer\s+review|مراجع[ةه]\s+(?:التصميم|الوثيق|مع\s+)|feedback.*(?:design|تصميم)",
    re.IGNORECASE,
)
_TEST_DOC_PATTERN = re.compile(
    r"test\s+(?:plan|report|results?)|خطة\s+اختبار|تقرير\s+اختبار|نتائج\s+اختبار",
    re.IGNORECASE,
)
_REVIEW_EFFECTIVENESS_PATTERN = re.compile(
    r"review.*(?:effectiveness|requirements?|client)|مراجعة.*(?:فعالية|متطلبات|العميل)",
    re.IGNORECASE,
)
_CODE_CRITERION_PATTERN = re.compile(
    r"produce|implement|creat(?:e|ing)\s+(?:a\s+)?(?:game|program)|إنتاج\s+لعبة|تطوير\s+لعبة",
    re.IGNORECASE,
)
_TEST_CRITERION_PATTERN = re.compile(
    r"test(?:ing)?\s+(?:the\s+)?(?:game|program)|اختبار\s+(?:اللعبة|البرنامج|شامل)",
    re.IGNORECASE,
)


def _relative_parts(path: Path, root: Path) -> tuple[str, ...]:
    try:
        return path.relative_to(root).parts
    except ValueError:
        return path.parts


def resolve_student_submission_root(
    primary_path: str,
    *,
    student_name: str = "",
) -> Path:
    """Find batch student folder (exe/pck/project), not a deep Assets/ leaf only."""
    from app.godot_submission_utils import find_godot_submission_root

    return find_godot_submission_root(primary_path, student_name=student_name)


_FAST_SKIP_EXT = frozenset(
    {".exe", ".win", ".apk", ".ipa", ".pck", ".mp3", ".wav", ".ogg", ".m4a", ".zip", ".rar"}
)


def _bounded_submission_root(primary_path: str) -> Path:
    """
    Student bundle folder only — never walk uploads/students (full rglob there freezes PRO).
    """
    import re

    try:
        p = Path(primary_path).resolve()
    except OSError:
        p = Path(primary_path)
    cur = p.parent if p.is_file() else p
    for _ in range(6):
        if not cur.is_dir():
            break
        try:
            has_marker = any(
                next(cur.glob(pat), None) is not None
                for pat in (
                    "*.yyp", "*.gml", "*.gd", "project.godot", "*.exe", "*.pck",
                    "*.sb3", "*.sb2", "data.win",
                )
            )
        except OSError:
            has_marker = False
        if has_marker:
            return cur
        if re.match(r"^(bx\d+|batch_\d+)", cur.name, re.IGNORECASE):
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return p.parent if p.is_file() else p


def expand_submission_paths(
    paths: Sequence[str],
    *,
    primary_path: str = "",
    student_name: str = "",
    grading_mode: str = "deep",
) -> List[str]:
    """Include sibling exe/docs from student root when intake path is deep (e.g. Assets/)."""
    from app.grading_mode_policy import is_fast_grading_mode

    slim_paths = is_fast_grading_mode(grading_mode)
    seen: Set[str] = set()
    out: List[str] = []
    for raw in paths or []:
        try:
            rp = str(Path(raw).resolve())
        except OSError:
            rp = raw
        if rp not in seen and Path(rp).is_file():
            seen.add(rp)
            out.append(rp)
    if slim_paths:
        return out

    has_code = any(Path(p).suffix.lower() in _CODE_EXT for p in out)
    has_exe = any(Path(p).suffix.lower() in _EXE_EXT for p in out)
    if has_code and has_exe and len(out) >= 4:
        return out

    root = _bounded_submission_root(primary_path or (paths[0] if paths else ""))
    try:
        from app.godot_submission_utils import should_skip_grading_path

        _max_expand = 400
        for f in root.rglob("*"):
            if len(out) >= _max_expand:
                break
            if not f.is_file():
                continue
            if f.name.startswith("~$"):
                continue
            if any(part.lower() in _SKIP_DIRS for part in _relative_parts(f, root)):
                continue
            if should_skip_grading_path(f):
                continue
            ext = f.suffix.lower()
            if ext in _DOC_EXT | _CODE_EXT | _EXE_EXT:
                if ext == ".exe" and "unitycrashhandler" in f.name.lower():
                    continue
                if ext == ".exe":
                    try:
                        from app.archive_extraction_utils import is_primary_game_executable

                        if not is_primary_game_executable(str(f)):
                            continue
                    except Exception:
                        pass
                rp = str(f.resolve())
                if rp not in seen:
                    seen.add(rp)
                    out.append(rp)
    except OSError:
        pass
    return out


def _has_godot_export_bundle(paths: Sequence[str]) -> bool:
    """Shipped Godot game: .pck paired with .exe or .apk (export deliverable)."""
    exts = {Path(raw).suffix.lower() for raw in paths or [] if Path(raw).is_file()}
    return ".pck" in exts and (".exe" in exts or ".apk" in exts or ".aab" in exts)


def _godot_export_counts_as_source(paths: Sequence[str]) -> bool:
    """Export-only Godot (.pck + optional .exe) — align with artifact_inventory."""
    if _has_godot_export_bundle(paths):
        return True
    if any(Path(raw).name == "project.godot" for raw in paths or []):
        return True
    pck_paths = [Path(raw) for raw in paths or [] if Path(raw).suffix.lower() == ".pck"]
    if not pck_paths:
        return False
    try:
        from app.runtime_observation_sandbox import analyze_godot_pck
    except Exception:
        return False
    for pck in sorted(pck_paths, key=lambda p: p.stat().st_size if p.is_file() else 0, reverse=True)[:3]:
        try:
            analysis = analyze_godot_pck(pck)
        except Exception:
            continue
        if not analysis.get("valid"):
            continue
        signals = analysis.get("signals") or {}
        if signals.get("has_gdscript") or signals.get("has_scenes"):
            return True
    return False


def _classify_paths(paths: Sequence[str]) -> Dict[str, Any]:
    docs: List[str] = []
    code: List[str] = []
    exe: List[str] = []
    for raw in paths or []:
        p = Path(raw)
        ext = p.suffix.lower()
        name = p.name.lower()
        if name in _RUNNABLE_GAME_FILENAMES:
            exe.append(str(p))  # GameMaker exported build (data.win)
        elif ext in _RUNNABLE_GAME_EXT:
            # Scratch project: both a runnable deliverable and project source
            exe.append(str(p))
            code.append(str(p))
        elif ext in _DOC_EXT:
            docs.append(str(p))
        elif ext in _CODE_EXT:
            code.append(str(p))
        elif ext in _EXE_EXT and "unitycrashhandler" not in name:
            exe.append(str(p))
    has_godot_source = _godot_export_counts_as_source(paths)
    has_bundle = _has_godot_export_bundle(paths)
    from app.pro_evidence_signals import classify_named_docs

    named_docs = classify_named_docs(docs)
    return {
        "has_word_pdf": bool(docs),
        "has_source_code": bool(code) or has_godot_source,
        "has_executable": bool(exe),
        "has_godot_export_source": has_godot_source,
        "has_godot_export_bundle": has_bundle,
        "has_testing_doc": named_docs["has_testing_doc"],
        "has_peer_design_doc": named_docs["has_peer_design_doc"],
        "doc_paths": docs,
        "code_paths": code,
        "executable_paths": exe,
    }


def _criterion_requirements(criterion: Dict[str, Any]) -> List[str]:
    text = " ".join(
        str(criterion.get(k) or "")
        for k in ("criteria_level", "criteria_name", "criteria_description")
    )
    kp = criterion.get("key_points") or []
    if isinstance(kp, list):
        text += " " + " ".join(str(x) for x in kp)
    reqs: List[str] = []
    if _GDD_PATTERN.search(text) or normalize_level(criterion.get("criteria_level", "")) == "P3":
        reqs.append("gdd_document")
    if _PEER_PATTERN.search(text) or normalize_level(criterion.get("criteria_level", "")) == "P4":
        reqs.append("peer_review_document")
    if _CODE_CRITERION_PATTERN.search(text) or normalize_level(criterion.get("criteria_level", "")) == "P5":
        reqs.extend(["source_code", "executable"])
    if _TEST_CRITERION_PATTERN.search(text) or normalize_level(criterion.get("criteria_level", "")) == "P6":
        reqs.extend(["source_code", "testing_evidence"])
    if _REVIEW_EFFECTIVENESS_PATTERN.search(text) or normalize_level(criterion.get("criteria_level", "")) == "P7":
        reqs.append("review_document")
    if _TEST_DOC_PATTERN.search(text):
        reqs.append("testing_evidence")
    if not reqs and normalize_level(criterion.get("criteria_level", "")).startswith("M"):
        reqs.append("supporting_documentation")
    if not reqs and normalize_level(criterion.get("criteria_level", "")).startswith("D"):
        reqs.append("evaluative_documentation")
    return list(dict.fromkeys(reqs))


def normalize_level(level: str) -> str:
    s = (level or "").strip().upper()
    return s.split(".")[-1] if "." in s else s


def _artifact_satisfied(req: str, assets: Dict[str, Any]) -> bool:
    if req == "gdd_document":
        return bool(assets["has_word_pdf"])
    if req == "peer_review_document":
        return bool(assets.get("has_peer_design_doc")) or bool(assets["has_word_pdf"])
    if req == "review_document":
        return bool(assets["has_word_pdf"])
    if req == "source_code":
        return bool(assets["has_source_code"])
    if req == "executable":
        return bool(assets["has_executable"])
    if req == "testing_evidence":
        return bool(assets.get("has_testing_doc")) or bool(assets["has_executable"])
    if req in ("supporting_documentation", "evaluative_documentation"):
        return bool(assets["has_word_pdf"]) or bool(assets["has_source_code"])
    return True


def evaluate_evidence_completeness(
    *,
    grading_criteria: Sequence[Dict[str, Any]],
    submission_paths: Sequence[str],
    primary_path: str = "",
    student_name: str = "",
    strict_block: bool = False,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    intake_relative_paths: Optional[Sequence[str]] = None,
    runtime_observed: bool = False,
    gameplay_video_verified: bool = False,
) -> Dict[str, Any]:
    """
    Pre-grade evidence gate. Returns per-criterion missing artifacts + summary.
    strict_block=True would mark criteria as blocked (used only when configured).

    ``runtime_observed`` / ``gameplay_video_verified`` carry the governing-principle
    observations: each criterion gets an ``evidence_strength_score`` (0..1) and a
    ``decision_confidence`` band so downstream routing can target only low-confidence
    criteria with the slow verification path. A deterministically analysed gameplay
    video is treated as runtime-equivalent for execution criteria (P5/P6/P7/M3).
    """
    merged_paths = list(submission_paths or [])
    for rel in intake_relative_paths or []:
        if rel and rel not in merged_paths:
            merged_paths.append(rel)
    expanded = expand_submission_paths(
        merged_paths,
        primary_path=primary_path,
        student_name=student_name,
    )
    assets = _classify_paths(expanded)
    inv = artifact_inventory or {}
    if inv.get("has_executable_artifacts") or (inv.get("executable_artifacts") or {}).get("files"):
        assets["has_executable"] = True
    if inv.get("has_source_code_artifacts") or (inv.get("source_code") or {}).get("files"):
        assets["has_source_code"] = True
    if (inv.get("documentation") or {}).get("files"):
        assets["has_word_pdf"] = True
    # A deterministically verified gameplay video is runtime-equivalent: it satisfies
    # the same "executable / runnable build" requirement for closed/Linux engines.
    if gameplay_video_verified:
        assets["has_executable"] = True

    from app.evidence_strength import assess_criterion_evidence, profile_from_assets

    evidence_profile = profile_from_assets(
        assets,
        runtime_observed=runtime_observed,
        gameplay_video_verified=gameplay_video_verified,
    )

    per_criterion: List[Dict[str, Any]] = []
    missing_any = False
    low_confidence_levels: List[str] = []

    for crit in grading_criteria or []:
        level = str(crit.get("criteria_level") or "")
        reqs = _criterion_requirements(crit)
        missing = [r for r in reqs if not _artifact_satisfied(r, assets)]
        if missing:
            missing_any = True
        crit_text = " ".join(
            str(crit.get(k) or "")
            for k in ("criteria_level", "criteria_name", "criteria_description")
        )
        verdict = assess_criterion_evidence(
            criterion_text=crit_text, profile=evidence_profile
        )
        if verdict["decision_confidence"] == "low":
            low_confidence_levels.append(level)
        per_criterion.append(
            {
                "criteria_level": level,
                "required_artifacts": reqs,
                "missing_artifacts": missing,
                "satisfied": not missing,
                "blocked_by_gate": bool(strict_block and missing),
                "evidence_strength_score": verdict["evidence_strength_score"],
                "decision_confidence": verdict["decision_confidence"],
                "command_verb": verdict["command_verb"],
                "command_verb_depth": verdict["command_verb_depth"],
                "required_strength": verdict["required_strength"],
                "needs_deeper_verification": verdict["needs_deeper_verification"],
            }
        )

    return {
        "gate_version": GATE_VERSION,
        "strict_block": strict_block,
        "submission_path_count": len(expanded),
        "assets_detected": {
            "word_pdf": assets["has_word_pdf"],
            "source_code": assets["has_source_code"],
            "executable": assets["has_executable"],
            "runtime_observed": runtime_observed,
            "gameplay_video_verified": gameplay_video_verified,
        },
        "evidence_profile": {
            "strongest_tier": compute_strongest_tier(evidence_profile),
            "active_tiers": evidence_profile.active_tiers(),
        },
        "per_criterion": per_criterion,
        "has_gaps": missing_any,
        "low_confidence_levels": low_confidence_levels,
        "missing_summary_ar": _missing_summary_ar(per_criterion),
        "expanded_paths_sample": expanded[:12],
    }


def compute_strongest_tier(profile: Any) -> Optional[str]:
    tiers = profile.active_tiers()
    if not tiers:
        return None
    from app.evidence_strength import TIER_WEIGHTS

    return max(tiers, key=lambda t: TIER_WEIGHTS.get(t, 0.0))


def _missing_summary_ar(per_criterion: List[Dict[str, Any]]) -> List[str]:
    labels = {
        "gdd_document": "وثيقة GDD (Word/PDF)",
        "peer_review_document": "توثيق مراجعة الأقران",
        "review_document": "تقرير مراجعة فعالية اللعبة",
        "source_code": "كود مصدري",
        "executable": "ملف تنفيذي (.exe/.apk)",
        "testing_evidence": "أدلة اختبار (مستند أو playtest)",
        "supporting_documentation": "توثيق داعم",
        "evaluative_documentation": "توثيق تقييمي",
    }
    lines: List[str] = []
    for row in per_criterion:
        if not row.get("missing_artifacts"):
            continue
        lv = row.get("criteria_level") or "?"
        parts = [labels.get(m, m) for m in row.get("missing_artifacts") or []]
        lines.append(f"{lv}: ينقص — {', '.join(parts)}")
    return lines


def attach_evidence_completeness_to_snapshot(
    grading_result: Dict[str, Any],
    gate_report: Dict[str, Any],
) -> None:
    """Persist gate report on grading snapshot (non-destructive)."""
    grading_result["evidence_completeness_gate"] = gate_report
    if gate_report.get("has_gaps"):
        notice = grading_result.setdefault("grading_coverage_notice", {})
        items = list(notice.get("items") or [])
        for line in gate_report.get("missing_summary_ar") or []:
            items.append({"kind": "evidence_completeness", "message_ar": line})
        notice["items"] = items
        notice["has_gaps"] = True
