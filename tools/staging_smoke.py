#!/usr/bin/env python3
"""Staging deployment smoke checks — API layer only."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def _get(url: str, timeout: float = 10.0) -> tuple[int, dict | list | str]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        try:
            return resp.status, json.loads(body)
        except json.JSONDecodeError:
            return resp.status, body


def check(name: str, url: str) -> bool:
    try:
        status, payload = _get(url)
    except urllib.error.URLError as exc:
        print(f"FAIL  {name}: {exc}")
        return False
    if status != 200:
        print(f"FAIL  {name}: HTTP {status}")
        return False
    print(f"OK    {name}")
    if name == "contracts_validate" and isinstance(payload, dict) and not payload.get("ok"):
        print(f"      contracts not ok: {payload}")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Staging API smoke checks")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    checks = [
        ("health", f"{base}/api/health"),
        ("ready", f"{base}/api/ready"),
        ("contracts_validate", f"{base}/api/contracts/validate"),
        ("contracts_freeze", f"{base}/api/contracts/freeze"),
        ("ops_sla", f"{base}/api/ops/sla"),
        ("ops_dashboard", f"{base}/api/ops/dashboard"),
    ]

    passed = sum(check(name, url) for name, url in checks)
    total = len(checks)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
