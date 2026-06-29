"""GameMaker .yyz archive extraction — unpack to workspace, no IDE build."""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Dict, Optional


def extract_yyz_archive(yyz_path: Path, dest_dir: Path) -> Dict[str, Any]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    if not yyz_path.is_file():
        return {"success": False, "error": "yyz_missing"}

    try:
        with zipfile.ZipFile(yyz_path, "r") as zf:
            members = zf.namelist()
            if len(members) > 5000:
                return {"success": False, "error": "yyz_too_many_entries", "count": len(members)}
            total = 0
            for member in members:
                info = zf.getinfo(member)
                total += info.file_size
                if total > 500 * 1024 * 1024:
                    return {"success": False, "error": "yyz_size_limit_exceeded"}
            zf.extractall(dest_dir)
    except zipfile.BadZipFile:
        return {"success": False, "error": "yyz_bad_zip"}
    except OSError as exc:
        return {"success": False, "error": str(exc)}

    yyp_files = list(dest_dir.rglob("*.yyp"))
    return {
        "success": True,
        "extracted_to": str(dest_dir),
        "entry_count": len(members),
        "yyp_files": [str(p) for p in yyp_files[:5]],
        "primary_yyp": str(yyp_files[0]) if yyp_files else None,
    }


def find_yyp_after_extract(extract_result: Dict[str, Any]) -> Optional[Path]:
    primary = extract_result.get("primary_yyp")
    if primary and Path(primary).is_file():
        return Path(primary)
    extracted = extract_result.get("extracted_to")
    if not extracted:
        return None
    for fp in Path(extracted).rglob("*.yyp"):
        return fp
    return None
