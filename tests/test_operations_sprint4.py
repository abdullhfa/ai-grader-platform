"""Phase 5 Sprint 4 — operations, SSO, RBAC tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_rbac_seed_and_assign(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from app.database import SessionLocal, init_db
    from app.auth.permissions_store import (
        assign_user_role,
        get_primary_governance_role,
        seed_rbac_defaults,
        user_has_permission,
    )
    from app.models import User, UserRole

    init_db()
    db = SessionLocal()
    try:
        seed_rbac_defaults(db)
        user = User(
            email="examiner@test.local",
            first_name="Ex",
            last_name="Am",
            role=UserRole.USER,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assign_user_role(db, user_id=int(user.id), role_name="examiner", source="test")
        assert get_primary_governance_role(db, int(user.id)) == "examiner"
        assert user_has_permission(db, int(user.id), "override_grade")
    finally:
        db.close()


def test_resolve_governance_role_db_backed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from app.database import SessionLocal, init_db
    from app.auth.permissions_store import assign_user_role, seed_rbac_defaults
    from app.governance.permissions import GovernanceRole, resolve_governance_role
    from app.models import User, UserRole

    init_db()
    db = SessionLocal()
    try:
        seed_rbac_defaults(db)
        user = User(email="senior@test.local", role=UserRole.USER, is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        assign_user_role(db, user_id=int(user.id), role_name="senior_examiner")
        role = resolve_governance_role(user, db=db)
        assert role == GovernanceRole.SENIOR_EXAMINER
    finally:
        db.close()


def test_oidc_provider_azure_config(monkeypatch):
    from app.auth.oidc_provider import get_active_oidc_provider

    monkeypatch.setenv("AI_GRADER_SSO_PROVIDER", "azure")
    monkeypatch.setenv("AI_GRADER_AZURE_CLIENT_ID", "client")
    monkeypatch.setenv("AI_GRADER_AZURE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("AI_GRADER_AZURE_TENANT_ID", "tenant-id")
    get_active_oidc_provider.cache_clear() if hasattr(get_active_oidc_provider, "cache_clear") else None
    cfg = get_active_oidc_provider()
    assert cfg is not None
    assert cfg.name == "azure"
    assert cfg.token_endpoint is not None
    assert "tenant-id" in cfg.token_endpoint


def test_role_mapper_from_groups():
    from app.auth.role_mapper import map_claims_to_roles

    roles = map_claims_to_roles({"groups": ["examiner-pool"], "email": "x@test.local"})
    assert "student" in roles


def test_role_mapper_group_map_env(monkeypatch):
    from app.auth.role_mapper import map_claims_to_roles

    monkeypatch.setenv("AI_GRADER_SSO_GROUP_ROLE_MAP", '{"examiner-pool":"examiner"}')
    roles = map_claims_to_roles({"groups": ["examiner-pool"], "email": "x@test.local"})
    assert "examiner" in roles


def test_correlation_context():
    from app.ops.correlation import CorrelationContext, bind_submission, get_correlation_ids, set_correlation

    ctx = CorrelationContext(trace_id="trace123", submission_id="sub1")
    set_correlation(ctx)
    ids = get_correlation_ids()
    assert ids["trace_id"] == "trace123"
    bound = bind_submission("sub2", replay_id="replay1")
    assert bound.submission_id == "sub2"
    assert bound.replay_id == "replay1"


def test_replay_archival_dry_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    snap = tmp_path / "uploads" / "replay_snapshots" / "student" / "sess1"
    snap.mkdir(parents=True)
    (snap / "deterministic_hash.json").write_text("{}", encoding="utf-8")

    from app.ops.replay_archival import apply_archival_policy

    result = apply_archival_policy(dry_run=True)
    assert result["status"] == "ok"
    assert result["count"] >= 1
    assert result["actions"][0]["tier"] == "hot"


def test_operational_dashboard():
    from app.observability.metrics import record_submission_rejected
    from app.ops.operational_metrics import operational_dashboard_snapshot

    record_submission_rejected("path_traversal")
    dash = operational_dashboard_snapshot()
    assert dash["schema"] == "operational_dashboard_v1"
    assert "runtime_failures" in dash["metrics"]


def test_backup_policy_structure():
    from app.ops.backup_policy import backup_policy

    policy = backup_policy()
    assert policy["schema"] == "backup_policy_v1"
    assert "postgresql" in policy
    assert "audit_logs" in policy


def test_auth_package_imports():
    from app.auth import create_session, get_current_user, hash_password

    assert callable(create_session)
    assert callable(hash_password)
