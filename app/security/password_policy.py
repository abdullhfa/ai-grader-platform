"""Registration password policy."""
from __future__ import annotations

import re
from typing import List, Tuple

_MIN_LEN = 8


def validate_password(password: str) -> Tuple[bool, List[str]]:
    """Return (ok, list of Arabic error messages)."""
    errors: List[str] = []
    if len(password) < _MIN_LEN:
        errors.append(f"كلمة المرور يجب أن تكون { _MIN_LEN } أحرف على الأقل")
    if not re.search(r"[A-Z]", password):
        errors.append("يجب أن تحتوي على حرف لاتيني كبير واحد على الأقل")
    if not re.search(r"[a-z]", password):
        errors.append("يجب أن تحتوي على حرف لاتيني صغير واحد على الأقل")
    if not re.search(r"\d", password):
        errors.append("يجب أن تحتوي على رقم واحد على الأقل")
    return (len(errors) == 0, errors)
