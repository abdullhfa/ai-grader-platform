"""
Unified grading pipeline — single production entry for batch and single-student grading.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from app.batch_grader import grade_batch_async
from app.core.grading_context import SubmissionProcessingContext
from app.core.logging_setup import append_audit_record, log_structured
from app.core.production_config import get_production_config
from app.evidence_completeness_gate import expand_submission_paths
from app.grading_mode_policy import enrich_student_submission_flags

logger = logging.getLogger("ai_grader.pipeline")


def _prepare_student_files(
    student_files: List[Dict[str, Any]],
    *,
    grading_mode: str = "deep",
) -> List[Dict[str, Any]]:
    prepared: List[Dict[str, Any]] = []
    for info in student_files:
        row = dict(info)
        paths = row.get("submission_paths") or [row.get("path", "")]
        row["submission_paths"] = expand_submission_paths(
            list(paths),
            primary_path=str(row.get("path") or ""),
            student_name=str(row.get("name") or ""),
            grading_mode=grading_mode,
        )
        enrich_student_submission_flags(row)
        prepared.append(row)
    return prepared


async def run_batch_grading(
    student_files: List[Dict[str, Any]],
    reference_solution: Dict[str, Any],
    grading_criteria: List[Dict[str, Any]],
    *,
    selected_criteria: Optional[List[str]] = None,
    skip_grading_cache: bool = False,
    progress_callback=None,
    start_callback=None,
    phase_callback: Optional[Callable[[str, str, float], Any]] = None,
    max_retries: Optional[int] = None,
    grading_mode: str = "deep",
    cancel_check: Optional[Callable[[], bool]] = None,
) -> List[Dict[str, Any]]:
    """
    Production batch grading with retries and audit logging.
    """
    cfg = get_production_config()
    retries = max_retries if max_retries is not None else cfg.grading_max_retries
    ctx = SubmissionProcessingContext.from_wire(grading_mode)
    prepared = _prepare_student_files(student_files, grading_mode=ctx.wire_mode)
    sel = selected_criteria if selected_criteria is not None else []

    last_error: Optional[Exception] = None
    for attempt in range(max(1, retries + 1)):
        try:
            results = await grade_batch_async(
                prepared,
                reference_solution,
                grading_criteria,
                selected_criteria=sel,
                grading_mode=ctx.wire_mode,
                skip_grading_cache=skip_grading_cache,
                progress_callback=progress_callback,
                start_callback=start_callback,
                phase_callback=phase_callback,
                cancel_check=cancel_check,
            )
            log_structured(
                "batch_grading_complete",
                students=len(results),
                attempt=attempt + 1,
                success=sum(1 for r in results if r.get("success")),
                grading_mode=ctx.grading_mode.value,
                profile_version=ctx.profile.version,
            )
            append_audit_record(
                cfg.audit_log_path,
                {
                    "event": "batch_grading_complete",
                    "students": len(results),
                    "attempt": attempt + 1,
                },
            )
            return results
        except Exception as exc:
            last_error = exc
            logger.exception("batch grading attempt %d failed", attempt + 1)
            log_structured("batch_grading_failed", attempt=attempt + 1, error=str(exc), level=logging.ERROR)
            if attempt >= retries:
                raise
            await asyncio.sleep(min(2 ** attempt, 8))

    raise RuntimeError(f"batch grading failed: {last_error}")


async def run_single_student_grading(
    student_info: Dict[str, Any],
    reference_solution: Dict[str, Any],
    grading_criteria: List[Dict[str, Any]],
    **kwargs: Any,
) -> Dict[str, Any]:
    results = await run_batch_grading(
        [student_info],
        reference_solution,
        grading_criteria,
        **kwargs,
    )
    return results[0] if results else {"success": False, "error": "empty_results"}
