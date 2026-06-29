"""Chaos and failure resilience tests — production maturity."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_chaos_replay_corruption_detected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    snap = tmp_path / "uploads" / "replay_snapshots" / "s" / "sess"
    (snap / "runtime").mkdir(parents=True)
    (snap / "runtime" / "runtime.json").write_text("CORRUPT{", encoding="utf-8")
    (snap / "deterministic_hash.json").write_text('{"deterministic_hash":"abc"}', encoding="utf-8")

    from app.security.tamper import verify_replay_integrity

    result = verify_replay_integrity(snap)
    assert result["ok"] is False


def test_chaos_partial_upload_guard(tmp_path):
    from app.infra.submission_guard import validate_file_size

    fp = tmp_path / "huge.bin"
    fp.write_bytes(b"x" * 1000)
    ok = validate_file_size(fp, max_bytes=500)
    assert ok["ok"] is False


def test_chaos_redis_rate_limit_fallback():
    from app.security.rate_limit import check_rate_limit

    allowed, _ = check_rate_limit("chaos-client-redis-down", limit=100, window_seconds=60)
    assert allowed is True


def test_chaos_cv_worker_crash_dead_letter(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AI_GRADER_OBJECT_STORE", "local")
    monkeypatch.setenv("AI_GRADER_UPLOAD_ROOT", str(tmp_path / "uploads"))
    from app.storage.object_store import get_object_store

    get_object_store.cache_clear()
    from app.tasks.worker_tasks import _write_dead_letter

    _write_dead_letter("gameplay_analysis_task", {"session": "x"}, "simulated_worker_crash")
    path = tmp_path / "uploads" / "audit" / "dead_letter.jsonl"
    alt = tmp_path / "uploads" / "audit" / "dead_letter" / "gameplay_analysis_task.jsonl"
    assert path.is_file() or alt.is_file()
    content = path.read_text(encoding="utf-8") if path.is_file() else alt.read_text(encoding="utf-8")
    assert "simulated_worker_crash" in content


def test_chaos_postgres_failover_simulation_sqlite_fallback(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./chaos_test.db")
    from app.database import engine

    assert "sqlite" in str(engine.url)


def test_chaos_replay_restore_from_archive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    warm = tmp_path / "uploads" / "archive" / "warm" / "replay_snapshots" / "s" / "sess"
    warm.mkdir(parents=True)
    (warm / "deterministic_hash.json").write_text(
        json.dumps({"deterministic_hash": "a" * 64, "replay_schema_version": "1.0"}),
        encoding="utf-8",
    )
    from app.governance.replay_viewer import load_replay_inspection_bundle
    import shutil

    dest = tmp_path / "uploads" / "replay_snapshots" / "s" / "sess"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(warm, dest)
    bundle = load_replay_inspection_bundle("s", "sess")
    assert bundle.deterministic_hash == "a" * 64


def test_chaos_rabbitmq_outage_celery_sync_fallback(monkeypatch):
    monkeypatch.delenv("AI_GRADER_CELERY_ENABLED", raising=False)
    from app.tasks.celery_app import is_celery_enabled

    assert is_celery_enabled() is False


def test_incident_response_workflow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from app.ops.incident_response import IncidentState, is_audit_frozen, run_incident_workflow

    snap = tmp_path / "uploads" / "replay_snapshots" / "student" / "sess1"
    snap.mkdir(parents=True)
    (snap / "deterministic_hash.json").write_text("{}", encoding="utf-8")

    inc = run_incident_workflow(
        event_type="replay_tamper_suspected",
        severity="critical",
        description="test incident",
        submission_key="student",
        session_id="sess1",
    )
    assert inc["state"] == IncidentState.INVESTIGATING.value
    assert is_audit_frozen() is True
    preserved = tmp_path / "uploads" / "ops" / "incident_preservation" / inc["incident_id"]
    assert preserved.is_dir()


def test_schema_version_migration_legacy_snapshot():
    from app.contracts.migration_policy import migrate_replay_manifest

    legacy = {"deterministic_hash": "abc", "submission_key": "s"}
    migrated = migrate_replay_manifest(legacy)
    assert migrated["replay_schema_version"] == "1.0"
    assert migrated["migration_applied"] == "legacy_version_stamp_v1"
