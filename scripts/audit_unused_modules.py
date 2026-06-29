"""Find app/*.py modules with no inbound imports from project code."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}


def path_to_module(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = rel.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def iter_py_files() -> list[Path]:
    out: list[Path] = []
    for p in ROOT.rglob("*.py"):
        if any(s in p.parts for s in SKIP_DIRS):
            continue
        out.append(p)
    return out


def collect_imports(text: str) -> set[str]:
    found: set[str] = set()
    for m in re.finditer(
        r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
        text,
        re.MULTILINE,
    ):
        mod = (m.group(1) or m.group(2) or "").strip()
        if mod.startswith("app."):
            found.add(mod)
        elif mod == "app":
            found.add("app")
    return found


def main() -> None:
    py_files = iter_py_files()
    app_modules = {
        path_to_module(p)
        for p in py_files
        if path_to_module(p).startswith("app.")
    }

    # Who imports whom (module -> set of imported app modules)
    imported_by: dict[str, set[str]] = {m: set() for m in app_modules}
    file_imports: dict[str, set[str]] = {}

    for p in py_files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        src = path_to_module(p)
        imps = collect_imports(text)
        file_imports[src] = imps
        for imp in imps:
            if imp in imported_by:
                imported_by[imp].add(src)
            # also mark parent packages as referenced
            parts = imp.split(".")
            for i in range(len(parts), 1, -1):
                pkg = ".".join(parts[:i])
                if pkg in imported_by:
                    imported_by[pkg].add(src)

    seeds = {"main", "app.routes.register", "app.tasks.celery_app", "app.tasks.worker_tasks"}
    for p in py_files:
        if p.name.startswith("test_") or p.parent.name == "tests":
            seeds.add(path_to_module(p))
    tools_audit = ROOT / "tools" / "audit_batch_submissions.py"
    if tools_audit.exists():
        seeds.add(path_to_module(tools_audit))

    reachable: set[str] = set()
    queue = [s for s in seeds if s in app_modules or s == "main"]
    if "main" not in queue:
        queue.append("main")

    while queue:
        cur = queue.pop()
        if cur in reachable:
            continue
        reachable.add(cur)
        for imp in file_imports.get(cur, set()):
            if imp.startswith("app.") and imp not in reachable:
                queue.append(imp)
            # submodules
            for mod in app_modules:
                if mod.startswith(imp + ".") and mod not in reachable:
                    queue.append(mod)

    # Expand: any module imported by reachable is reachable
    changed = True
    while changed:
        changed = False
        for src in list(reachable):
            for imp in file_imports.get(src, set()):
                if imp.startswith("app.") and imp not in reachable:
                    reachable.add(imp)
                    changed = True
                for mod in app_modules:
                    if mod.startswith(imp + ".") and mod not in reachable:
                        reachable.add(mod)
                        changed = True

    orphan = sorted(m for m in app_modules if m not in reachable)

    report_path = ROOT / "scripts" / "unused-modules-report.txt"
    lines = [
        f"app modules: {len(app_modules)}",
        f"reachable from main/tests: {len(reachable & app_modules)}",
        f"orphan candidates (import graph): {len(orphan)}",
        "",
        "=== ORPHANS (import graph) ===",
        *orphan,
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines[:5]))
    print(f"... report: {report_path}")


if __name__ == "__main__":
    main()
