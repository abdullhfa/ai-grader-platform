#!/usr/bin/env python3
"""Pre-deploy checks before staging go-live — no Docker required for local gates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_TOOLS_DIR = Path(__file__).resolve().parent


def _load_docker_env():
    import importlib.util

    path = _TOOLS_DIR / "docker_env.py"
    spec = importlib.util.spec_from_file_location("docker_env", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_de = _load_docker_env()
docker_daemon_ready = _de.docker_daemon_ready
ensure_docker_cli = _de.ensure_docker_cli


def ok(msg: str) -> None:
    print(f"OK    {msg}")


def fail(msg: str) -> None:
    print(f"FAIL  {msg}")


def check_docker() -> bool:
    if not ensure_docker_cli():
        fail("docker CLI not found — install Docker Desktop or deploy on a host with Docker")
        return False
    ok("docker CLI available")
    if not docker_daemon_ready():
        fail("docker daemon not running — start Docker Desktop until status is Running")
        return False
    ok("docker daemon ready")
    return True


def check_compose_files() -> bool:
    base = ROOT / "infra" / "docker"
    required = [
        base / "docker-compose.yml",
        base / "docker-compose.ops.yml",
        base / "docker-compose.staging.yml",
    ]
    missing = [p for p in required if not p.is_file()]
    if missing:
        for p in missing:
            fail(f"missing compose file: {p}")
        return False
    ok("staging compose stack files present")
    return True


def check_contracts() -> bool:
    manifest = ROOT / "schemas" / "CONTRACT_MANIFEST.json"
    if not manifest.is_file():
        fail("CONTRACT_MANIFEST.json missing")
        return False
    text = manifest.read_text(encoding="utf-8")
    if '"status": "frozen"' not in text:
        fail("contracts not frozen")
        return False
    ok("contract manifest frozen")
    return True


def check_pytest_gates() -> bool:
    cmd = [sys.executable, "-m", "pytest", "tests/test_chaos_resilience.py", "tests/test_pentest_hardening.py", "-q"]
    print("RUN   " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        fail("chaos/pentest regression failed")
        print(result.stdout)
        print(result.stderr)
        return False
    ok("chaos + pentest regression passed")
    return True


def main() -> int:
    print("Go-Live preflight — execute → validate → observe → harden\n")
    results = [
        check_compose_files(),
        check_contracts(),
        check_pytest_gates(),
        check_docker(),
    ]
    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} checks passed")
    if not results[2]:
        return 1
    if not results[3]:
        print("\nNote: local pytest gates passed; start Docker Desktop then re-run deploy.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
