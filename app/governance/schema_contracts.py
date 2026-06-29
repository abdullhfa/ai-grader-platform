"""JSON Schema contract validation for institutional stability."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


@lru_cache(maxsize=16)
def load_schema(name: str) -> Dict[str, Any]:
    path = SCHEMA_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"schema not found: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_against_schema(payload: Any, schema_name: str) -> Tuple[bool, List[str]]:
    """Validate payload; returns (ok, errors). Uses jsonschema if installed."""
    schema = load_schema(schema_name)
    try:
        import jsonschema
    except ImportError:
        return True, ["jsonschema not installed — validation skipped"]

    validator = jsonschema.Draft7Validator(schema)
    errors = [e.message for e in validator.iter_errors(payload)]
    return len(errors) == 0, errors


def list_contract_schemas() -> List[str]:
    if not SCHEMA_DIR.is_dir():
        return []
    return sorted(p.name for p in SCHEMA_DIR.glob("*.schema.json"))
