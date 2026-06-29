"""
Structured production logging for grading and runtime subsystems.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_CONFIGURED = False


def configure_production_logging(level: int = logging.INFO) -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger("ai_grader")
    if _CONFIGURED:
        return logger
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    if not logger.handlers:
        logger.addHandler(handler)
    _CONFIGURED = True
    return logger


def get_logger(name: str = "ai_grader") -> logging.Logger:
    configure_production_logging()
    return logging.getLogger(name)


def log_structured(
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    payload: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": event,
        **fields,
    }
    get_logger().log(level, json.dumps(payload, ensure_ascii=False, default=str))


def append_audit_record(path: str, record: Dict[str, Any]) -> None:
    """Append-only JSONL audit trail."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **record,
    }
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
