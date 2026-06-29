"""One-off: remove routes migrated to app/routes/* from main.py."""
from __future__ import annotations

from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "main.py"
text = MAIN.read_text(encoding="utf-8")
lines = text.splitlines(keepends=True)

# Ranges to drop (1-based inclusive) — bottom-up to preserve indices
DROP_RANGES = [
    (9016, 9069),
    (3760, 4014),
    (3157, 3757),
    (620, 676),
    (271, 293),
]

for start, end in sorted(DROP_RANGES, reverse=True):
    del lines[start - 1 : end]

MAIN.write_text("".join(lines), encoding="utf-8")
print(f"Stripped {len(DROP_RANGES)} blocks from main.py")
