"""Phenomenology manifest loader — compression, not abstraction."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Tuple

MANIFEST_PATH = (
    Path(__file__).resolve().parent
    / "calibration"
    / "PHENOMENOLOGY_MANIFEST_v1.json"
)
MANIFEST_ID = "PHENOMENOLOGY_MANIFEST_v1"


@lru_cache(maxsize=1)
def load_manifest() -> Dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def domain(name: str) -> Dict[str, Any]:
    d = load_manifest().get("domains", {}).get(name)
    if not d:
        raise KeyError(f"unknown phenomenology domain: {name}")
    return d


def descriptors(domain_name: str) -> FrozenSet[str]:
    return frozenset(domain(domain_name).get("descriptors") or [])


def forbidden_escalations(domain_name: str) -> FrozenSet[str]:
    return frozenset(domain(domain_name).get("forbidden_escalations") or [])


def escalation_pairs(domain_name: str) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for row in domain(domain_name).get("escalation_pairs") or []:
        pairs.append((row["phenomenology"], row["forbidden"]))
    return pairs


def domain_invariant(domain_name: str) -> str:
    return str(domain(domain_name).get("invariant_en") or "")
