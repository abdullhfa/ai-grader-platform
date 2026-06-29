#!/usr/bin/env python3
"""Phase 2 — verify operational signals and platform heartbeat KPIs."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_kpis(base_url: str) -> int:
    base = base_url.rstrip("/")
    failures = 0

    try:
        dashboard = fetch_json(f"{base}/api/ops/dashboard")
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"FAIL  ops dashboard: {exc}")
        return 1

    metrics = dashboard.get("metrics") or {}
    health = dashboard.get("health_indicators") or {}

    checks = [
        ("replay_mismatch", metrics.get("replay_mismatch", 0), 0, "=="),
        ("runtime_failures", metrics.get("runtime_failures", 0), None, "report"),
        ("hallucination_manual_review", metrics.get("hallucination_manual_review", 0), None, "report"),
        ("suspicious_submissions", metrics.get("suspicious_submissions", 0), None, "report"),
    ]

    print("Phase 2 — operational signals\n")
    for name, value, target, mode in checks:
        if mode == "==":
            if value == target:
                print(f"OK    {name} = {value} (target {target})")
            else:
                print(f"FAIL  {name} = {value} (target {target}) — PLATFORM HEARTBEAT VIOLATION")
                failures += 1
        else:
            print(f"INFO  {name} = {value}")

    for layer, status in health.items():
        if status == "healthy":
            print(f"OK    health.{layer} = {status}")
        else:
            print(f"WARN  health.{layer} = {status}")
            failures += 1

    try:
        contracts = fetch_json(f"{base}/api/contracts/validate")
        if contracts.get("ok"):
            print("OK    contracts_validate = ok")
        else:
            print(f"FAIL  contracts_validate: {contracts}")
            failures += 1
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"FAIL  contracts_validate: {exc}")
        failures += 1

    print(f"\n{'PASS' if failures == 0 else 'FAIL'}  {failures} KPI violation(s)")
    if failures:
        print("Action: POST /api/ops/incidents — audit freeze + preserve replays")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify staging operational KPIs (Phase 2)")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    return check_kpis(args.base_url)


if __name__ == "__main__":
    sys.exit(main())
