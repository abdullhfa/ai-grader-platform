"""Disaster recovery drills — restore replay, audit integrity, queue recovery."""
from __future__ import annotations

import json
import shutil
from pathlib import Path


def test_dr_restore_replay_archive(tmp_path, monkeypatch):
    """Simulate warm archive restore."""
    monkeypatch.chdir(tmp_path)
    warm = tmp_path / "uploads" / "archive" / "warm" / "replay_snapshots" / "student" / "sess1"
    warm.mkdir(parents=True)
    (warm / "deterministic_hash.json").write_text('{"deterministic_hash":"abc"}', encoding="utf-8")

    restored = tmp_path / "uploads" / "replay_snapshots" / "student" / "sess1"
    restored.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(warm, restored)

    assert (restored / "deterministic_hash.json").is_file()


def test_dr_audit_log_integrity_after_restore(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log = tmp_path / "uploads" / "governance" / "audit" / "sess1" / "audit_log.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text('{"action":"override_grade","actor":"e@test.local"}\n', encoding="utf-8")

    from app.security.tamper import verify_audit_log_integrity

    result = verify_audit_log_integrity(log)
    assert result["ok"] is True
    assert result["event_count"] == 1


def test_dr_rebuild_evidence_graph_from_snapshot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    base = tmp_path / "uploads" / "replay_snapshots" / "s" / "sess"
    (base / "evidence").mkdir(parents=True)
    graphs = [{"criterion_id": "C.P5", "nodes": [{"node_id": "n1", "claim": "win"}]}]
    (base / "evidence" / "evidence.json").write_text(json.dumps(graphs), encoding="utf-8")

    from app.governance.replay_viewer import load_replay_inspection_bundle

    bundle = load_replay_inspection_bundle("s", "sess")
    assert bundle.evidence is not None


def test_dr_dead_letter_queue_recovery(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "uploads" / "audit" / "dead_letter.jsonl"
    path.parent.mkdir(parents=True)
    row = {"task": "runtime_observation_task", "error": "timeout", "payload": {"paths": []}}
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    recovered = [json.loads(l) for l in lines]
    assert recovered[0]["task"] == "runtime_observation_task"
    assert recovered[0]["error"] == "timeout"
