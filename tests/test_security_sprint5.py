"""Phase 5 Sprint 5 — security hardening tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_secret_policy_validation():
    from app.security.secret_policy import validate_secret_policy

    result = validate_secret_policy(environment="development")
    assert result["policy"] == "secret_policy_v1"
    assert "ok" in result


def test_tamper_verification_hash_stable():
    from app.security.tamper import compute_tamper_verification_hash

    h1 = compute_tamper_verification_hash(
        artifact_type="replay_snapshot",
        payload={"a": 1},
        replay_hash="abc",
    )
    h2 = compute_tamper_verification_hash(
        artifact_type="replay_snapshot",
        payload={"a": 1},
        replay_hash="abc",
    )
    assert h1 == h2
    assert len(h1) == 64


def test_replay_tamper_detection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    snap = tmp_path / "uploads" / "replay_snapshots" / "s" / "sess"
    (snap / "runtime").mkdir(parents=True)
    sections = {"runtime": {"status": "ok"}}
    (snap / "runtime" / "runtime.json").write_text(json.dumps(sections["runtime"]), encoding="utf-8")

    from app.ai_reasoning.snapshots.deterministic_hash import compute_snapshot_hash
    from app.security.tamper import verify_replay_integrity

    digest = compute_snapshot_hash(sections)
    (snap / "deterministic_hash.json").write_text(
        json.dumps({"deterministic_hash": digest}), encoding="utf-8"
    )
    ok = verify_replay_integrity(snap)
    assert ok["ok"] is True

    (snap / "runtime" / "runtime.json").write_text('{"status":"tampered"}', encoding="utf-8")
    bad = verify_replay_integrity(snap)
    assert bad["ok"] is False
    assert bad["integrity"] == "tampered"


def test_yara_heuristic_detects_powershell(tmp_path):
    from app.security.scanning.yara_rules import scan_file_patterns

    fp = tmp_path / "malicious.txt"
    fp.write_bytes(b"Invoke-Expression $(cmd.exe)")
    result = scan_file_patterns(fp)
    assert result["flagged"] is True
    assert "powershell_invoke" in result["matches"]


def test_malware_pipeline_clean_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fp = tmp_path / "hello.py"
    fp.write_text("print('hello')\n", encoding="utf-8")

    from app.security.scanning.pipeline import scan_submission_path

    result = scan_submission_path(fp, submission_key="student1")
    assert result["status"] == "clean"
    assert result["quarantine_id"]


def test_malware_pipeline_rejects_blocklist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fp = tmp_path / "bad.exe"
    fp.write_bytes(b"fake exe content")

    from app.security.scanning.reputation import file_sha256

    digest = file_sha256(fp)
    blocklist = tmp_path / "uploads" / "security"
    blocklist.mkdir(parents=True)
    (blocklist / "malware_blocklist.json").write_text(
        json.dumps({"sha256": [digest]}), encoding="utf-8"
    )

    from app.security.scanning.pipeline import scan_submission_path

    result = scan_submission_path(fp)
    assert result["status"] == "rejected"


def test_security_audit_append_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from app.security.security_audit import log_security_action, read_security_audit

    log_security_action(action="export", actor="examiner@test.local", resource="/api/governance/export/x")
    log_security_action(action="replay_access", actor="examiner@test.local", resource="s/sess")
    events = read_security_audit()
    assert len(events) == 2
    assert events[0]["action"] == "export"


def test_rate_limit_in_memory():
    from app.security.rate_limit import check_rate_limit

    allowed, _ = check_rate_limit("test-client", limit=2, window_seconds=60)
    assert allowed is True
    allowed, _ = check_rate_limit("test-client", limit=2, window_seconds=60)
    assert allowed is True
    allowed, retry = check_rate_limit("test-client", limit=2, window_seconds=60)
    assert allowed is False
    assert retry >= 1


def test_vault_disabled_by_default():
    from app.security.vault_provider import load_from_vault, vault_enabled

    assert vault_enabled() is False
    assert load_from_vault("DATABASE_URL") is None
