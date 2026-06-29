"""Parse and repair JSON blobs from local/cloud LLM grading responses."""
from __future__ import annotations

import json
import re
from typing import Any, Dict


_JSON_STRING = r'"(?:[^"\\]|\\.)*"'


def extract_json_blob(response_text: str) -> str:
    """Pull the JSON object out of markdown fences or surrounding prose."""
    text = response_text or ""
    if "```json" in text:
        blob = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        blob = text.split("```", 1)[1].split("```", 1)[0].strip()
    else:
        start = text.find("{")
        end = text.rfind("}")
        blob = text[start : end + 1] if start != -1 and end != -1 else text
    blob = re.sub(
        r"<think>.*?</think>",
        "",
        blob,
        flags=re.DOTALL,
    ).strip()
    return blob


def repair_llm_json_string(raw: str) -> str:
    """
    Fix common LLM JSON mistakes (Ollama/Qwen often close objects with ]).
    """
    s = raw

    # "reasoning": "..." ]  →  "reasoning": "..." }
    for field in ("reasoning", "evidence", "overall_feedback"):
        s = re.sub(
            rf'("{field}"\s*:\s*{_JSON_STRING})\s*\]',
            r"\1}",
            s,
            flags=re.IGNORECASE,
        )

    # Trailing commas before } or ]
    s = re.sub(r",\s*([}\]])", r"\1", s)

    # Unescaped newlines inside double-quoted values
    def _escape_newlines(match: re.Match[str]) -> str:
        return match.group(0).replace("\n", "\\n").replace("\r", "")

    s = re.sub(
        rf'(?<=: ){_JSON_STRING}',
        _escape_newlines,
        s,
        flags=re.DOTALL,
    )
    return s


def _close_truncated_json(s: str) -> str:
    repair = s.rstrip().rstrip(",")
    in_str = False
    last_char = ""
    for ch in repair:
        if ch == '"' and last_char != "\\":
            in_str = not in_str
        last_char = ch
    if in_str:
        repair += '"'
    open_brackets = repair.count("[") - repair.count("]")
    open_braces = repair.count("{") - repair.count("}")
    repair += "]" * max(0, open_brackets)
    repair += "}" * max(0, open_braces)
    return repair


def parse_llm_grading_json(response_text: str) -> Dict[str, Any]:
    """Parse grading JSON with layered repair for malformed LLM output."""
    json_str = repair_llm_json_string(extract_json_blob(response_text))
    last_err: json.JSONDecodeError | None = None

    for attempt in range(3):
        candidate = json_str if attempt == 0 else _close_truncated_json(json_str)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_err = exc
            if attempt == 0:
                json_str = repair_llm_json_string(candidate)
                continue
            if attempt == 1:
                continue
    assert last_err is not None
    raise last_err
