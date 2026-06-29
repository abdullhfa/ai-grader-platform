"""Deterministic snapshot hashing."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_snapshot_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
