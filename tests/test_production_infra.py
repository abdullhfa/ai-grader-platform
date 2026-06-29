"""Phase 5 production infrastructure tests."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest


def test_submission_guard_rejects_path_traversal():
    from app.infra.submission_guard import validate_submission_paths

    result = validate_submission_paths(["../etc/passwd", "safe/project/main.py"])
    assert result["ok"] is False
    assert any("path_traversal" in issue for issue in result["issues"])


def test_submission_guard_rejects_suspicious_entries():
    from app.infra.submission_guard import validate_submission_paths

    result = validate_submission_paths(["project/launch.bat", "Assets/Player.cs"])
    assert result["ok"] is False
    assert any("suspicious_entry" in issue for issue in result["issues"])


def test_runtime_limits_from_env(monkeypatch):
    from app.infra.runtime_limits import get_runtime_limits

    monkeypatch.setenv("AI_GRADER_RUNTIME_CPU_LIMIT", "4")
    monkeypatch.setenv("AI_GRADER_RUNTIME_MEMORY_MB", "8192")
    monkeypatch.setenv("AI_GRADER_RUNTIME_TIMEOUT", "300")
    limits = get_runtime_limits("unity")
    assert limits.cpu_limit == 4.0
    assert limits.memory_limit_mb == 8192
    assert limits.timeout_seconds == 300
    assert "--network" in limits.docker_flags()


def test_object_store_local_roundtrip(tmp_path, monkeypatch):
    from app.storage.object_store import ObjectStore, get_object_store

    get_object_store.cache_clear()
    monkeypatch.setenv("AI_GRADER_OBJECT_STORE", "local")
    monkeypatch.setenv("AI_GRADER_UPLOAD_ROOT", str(tmp_path))

    store = get_object_store()
    store.ensure_bucket()
    uri = store.put_bytes("runtime_sessions/student1/s1/manifest.json", b'{"ok":true}')
    assert store.exists("runtime_sessions/student1/s1/manifest.json")
    assert store.get_bytes("runtime_sessions/student1/s1/manifest.json") == b'{"ok":true}'
    assert str(tmp_path) in uri


def test_replay_hash_is_deterministic():
    from app.ai_reasoning.snapshots.deterministic_hash import compute_snapshot_hash

    payload = {"events": [{"type": "win_detected", "t": 1.2}], "student": "A"}
    h1 = compute_snapshot_hash(payload)
    h2 = compute_snapshot_hash(json.loads(json.dumps(payload)))
    assert h1 == h2
    assert len(h1) == 64


def test_queue_routes_segmented():
    from app.tasks.queues import QUEUE_GAMEPLAY, QUEUE_REASONING, QUEUE_REPORT, TASK_ROUTES

    assert TASK_ROUTES["app.tasks.worker_tasks.evidence_reasoning_task"]["queue"] == QUEUE_REASONING
    assert TASK_ROUTES["app.tasks.worker_tasks.gameplay_analysis_task"]["queue"] == QUEUE_GAMEPLAY
    assert TASK_ROUTES["app.tasks.worker_tasks.report_generation_task"]["queue"] == QUEUE_REPORT


def test_docker_sandbox_host_fallback_when_disabled(monkeypatch, tmp_path):
    from app.infra.docker_sandbox import run_ephemeral_sandbox

    monkeypatch.delenv("AI_GRADER_DOCKER_SANDBOX", raising=False)
    result = run_ephemeral_sandbox(["echo", "hi"], workspace=tmp_path)
    assert result["status"] == "host_fallback"
    assert result["isolation"] == "none"


def test_async_reasoning_queue_helper_without_celery(monkeypatch):
    from app.ai_reasoning.orchestrator import queue_evidence_reasoning

    monkeypatch.delenv("AI_GRADER_CELERY_ENABLED", raising=False)
    out = queue_evidence_reasoning(
        submission_key="student",
        grading_result={"student_name": "student"},
    )
    assert out["status"] == "celery_disabled"


def test_metrics_prometheus_export():
    from app.observability.metrics import metrics, record_reasoning_outcome, record_submission_rejected

    record_reasoning_outcome("completed", manual_review=True)
    record_submission_rejected("path_traversal")
    text = metrics.prometheus_text()
    assert "evidence_reasoning_total" in text
    assert "submission_guard_rejections_total" in text
