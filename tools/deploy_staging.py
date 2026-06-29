#!/usr/bin/env python3
"""Deterministic staging deploy — reduces deployment drift and manual ops errors."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
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
wait_for_docker_daemon = _de.wait_for_docker_daemon

COMPOSE_DIR = ROOT / "infra" / "docker"
COMPOSE_FILES = [
    COMPOSE_DIR / "docker-compose.yml",
    COMPOSE_DIR / "docker-compose.ops.yml",
    COMPOSE_DIR / "docker-compose.staging.yml",
]


def run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"RUN   {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd or ROOT, check=check, text=True)


def compose_args(*args: str) -> list[str]:
    cmd = ["docker", "compose"]
    for path in COMPOSE_FILES:
        cmd.extend(["-f", str(path)])
    cmd.extend(args)
    return cmd


def wait_for_health(base_url: str, timeout_sec: int = 180) -> bool:
    deadline = time.time() + timeout_sec
    url = f"{base_url.rstrip('/')}/api/ready"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    print(f"OK    API ready at {url}")
                    return True
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            pass
        time.sleep(5)
    print(f"FAIL  API not ready within {timeout_sec}s ({url})")
    return False


def run_preflight(*, require_docker: bool) -> int:
    cmd = [sys.executable, str(ROOT / "tools" / "go_live_preflight.py")]
    result = subprocess.run(cmd, cwd=ROOT, text=True)
    if result.returncode == 1:
        return 1
    if require_docker and result.returncode == 2:
        return 2
    return 0


def run_smoke(base_url: str) -> int:
    cmd = [sys.executable, str(ROOT / "tools" / "staging_smoke.py"), "--base-url", base_url]
    result = subprocess.run(cmd, cwd=ROOT, text=True)
    return result.returncode


def write_deploy_record(base_url: str, action: str) -> None:
    manifest_path = ROOT / "schemas" / "CONTRACT_MANIFEST.json"
    manifest = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = {
        "phase": "go_live_execution",
        "action": action,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": base_url,
        "platform_version": manifest.get("platform_version"),
        "contract_status": manifest.get("status"),
        "compose_files": [str(p.relative_to(ROOT)).replace("\\", "/") for p in COMPOSE_FILES],
        "contract_manifest": "schemas/CONTRACT_MANIFEST.json",
        "next_steps": [
            "python tools/verify_operational_signals.py",
            "hand off infra/pentest/ to external team",
        ],
    }
    out = ROOT / "uploads" / "ops" / "last_staging_deploy.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"OK    deploy record written to {out.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy institutional staging stack")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--down", action="store_true", help="Stop staging stack")
    parser.add_argument("--pull", action="store_true", help="Pull images before up")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--wait-timeout", type=int, default=180)
    parser.add_argument("--wait-docker", type=int, default=180, help="Seconds to wait for Docker daemon")
    args = parser.parse_args()

    if not ensure_docker_cli():
        print("FAIL  docker CLI not found — install Docker Desktop or add docker to PATH")
        return 2

    if not docker_daemon_ready():
        print("WAIT  Docker daemon not ready — start Docker Desktop and wait...")
        if not wait_for_docker_daemon(timeout_sec=args.wait_docker):
            print("FAIL  Docker daemon not running — open Docker Desktop until status is Running")
            return 2
    print("OK    Docker daemon ready")

    for path in COMPOSE_FILES:
        if not path.is_file():
            print(f"FAIL  missing compose file: {path}")
            return 1

    if not args.skip_preflight:
        code = run_preflight(require_docker=True)
        if code != 0:
            return code

    if args.down:
        run(compose_args("down"), cwd=COMPOSE_DIR)
        write_deploy_record(args.base_url, "down")
        return 0

    up_cmd = compose_args("up", "-d")
    if not args.skip_build:
        up_cmd.append("--build")
    if args.pull:
        up_cmd.insert(2, "--pull")
    run(up_cmd, cwd=COMPOSE_DIR)

    if not wait_for_health(args.base_url, timeout_sec=args.wait_timeout):
        return 1

    if not args.skip_smoke and run_smoke(args.base_url) != 0:
        return 1

    write_deploy_record(args.base_url, "up")
    print("\nStaging deploy complete — execute → validate → observe → harden")
    print("Phase 2: python tools/verify_operational_signals.py --base-url", args.base_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
