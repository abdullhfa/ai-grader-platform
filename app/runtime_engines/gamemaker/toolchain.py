"""GameMaker installation discovery and source-project runtime preflight.

Universal path-independent discovery supporting GameMaker, GameMaker Studio 2,
GameMaker-LTS, custom installations, and automatic runtime verification.
"""

import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple


def _user_folder_is_authenticated(path: Optional[Path]) -> bool:
    if not path or not path.is_dir():
        return False
    if path.name.lower().startswith("unknownuser_"):
        return False
    return any(
        (path / marker).is_file()
        for marker in ("licence.plist", "license.plist", "licence.json", "license.json")
    )


def _find_user_folder() -> Optional[Path]:
    explicit = os.environ.get("AI_GRADER_GAMEMAKER_USER_FOLDER")
    if explicit:
        candidate = Path(explicit).expanduser()
        return candidate.resolve() if _user_folder_is_authenticated(candidate) else None
    for env_name in ("APPDATA", "LOCALAPPDATA"):
        base = os.environ.get(env_name)
        if not base:
            continue
        for product_root in sorted(Path(base).glob("GameMaker*"), reverse=True):
            if not product_root.is_dir():
                continue
            for candidate in product_root.iterdir():
                if _user_folder_is_authenticated(candidate):
                    return candidate.resolve()
    return None

class GameMakerToolchain:
    @property
    def installed(self) -> bool:
        """Backward-compatible flag used by preflight/tests and UI diagnostics."""
        return bool(self.ide_path or self.igor_path)

    @property
    def ready(self) -> bool:
        """True when Igor and a runtime are available for local Compile/Run."""
        return bool(self.installed and self.igor_path and self.runtime_root)

    def __init__(self, ide_path: Optional[Path], igor_path: Optional[Path], runtime_root: Optional[Path], user_folder: Optional[Path] = None, reason: Optional[str] = None):
        self.ide_path = ide_path
        self.igor_path = igor_path
        self.runtime_root = runtime_root
        self.user_folder = user_folder or _find_user_folder()
        self.reason = reason or (
            "ready"
            if self.ready
            else "gamemaker_not_installed"
            if not self.installed
            else "gamemaker_runtime_missing"
        )

    def to_dict(self) -> dict:
        return {
            "installed": self.installed,
            "ready": self.ready,
            "ide_path": str(self.ide_path) if self.ide_path else None,
            "igor_path": str(self.igor_path) if self.igor_path else None,
            "runtime_root": str(self.runtime_root) if self.runtime_root else None,
            "user_folder": str(self.user_folder) if self.user_folder else None,
            "reason": self.reason,
        }

def _registry_ide_candidates() -> List[Path]:
    """Universal registry and file-system search for GameMaker IDE executables."""
    out: List[Path] = []
    
    # 1. Windows Registry Uninstall & App Paths
    if os.name == "nt":
        try:
            import winreg
            uninstall_paths = [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
            ]
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                    for uninstall in uninstall_paths:
                        try:
                            root = winreg.OpenKey(hive, uninstall, 0, winreg.KEY_READ | view)
                        except OSError:
                            continue
                        try:
                            count = winreg.QueryInfoKey(root)[0]
                            for idx in range(count):
                                try:
                                    key = winreg.OpenKey(root, winreg.EnumKey(root, idx))
                                except OSError:
                                    continue
                                try:
                                    name = ""
                                    for field in ("DisplayName", "QuietDisplayName"):
                                        try:
                                            name = str(winreg.QueryValueEx(key, field)[0] or "")
                                            if name: break
                                        except OSError:
                                            pass
                                    if "gamemaker" not in name.lower() and "yoyo" not in name.lower():
                                        continue
                                    for field in ("InstallLocation", "DisplayIcon", "UninstallString", "Inno Setup: App Path"):
                                        try:
                                            val = str(winreg.QueryValueEx(key, field)[0] or "").strip()
                                            if not val:
                                                continue
                                            if val.startswith('"'):
                                                clean = val[1:].split('"', 1)[0]
                                            else:
                                                clean = val.split(" ", 1)[0]
                                            p = Path(clean)
                                            if p.suffix.lower() == ".exe":
                                                if "gamemaker" in p.name.lower() or "igor" in p.name.lower():
                                                    out.append(p)
                                                p = p.parent
                                            if p.is_dir():
                                                out.append(p)
                                                for exe in p.glob("*.exe"):
                                                    if "gamemaker" in exe.name.lower() or "studio" in exe.name.lower():
                                                        out.append(exe)
                                        except OSError:
                                            pass
                                finally:
                                    winreg.CloseKey(key)
                        finally:
                            winreg.CloseKey(root)
        except Exception:
            pass

    # 2. Standard Program Files, ProgramData, AppData Roots
    search_roots = []
    for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA"):
        val = os.environ.get(env_name)
        if val and Path(val).exists():
            search_roots.append(Path(val))
    
    # Environment variables are authoritative.  This keeps discovery portable
    # and lets tests (and isolated workers) provide a clean search root without
    # accidentally finding a different GameMaker installation on the host.
    # Normal Windows installations expose these same locations through
    # PROGRAMFILES/PROGRAMDATA/APPDATA, so no fixed C:\ fallback is required.

    for sr in search_roots:
        try:
            for sub in sr.glob("*GameMaker*"):
                if sub.is_file() and sub.suffix.lower() == ".exe":
                    out.append(sub)
                elif sub.is_dir():
                    out.append(sub)
                    for exe in sub.glob("**/*.exe"):
                        if "gamemaker" in exe.name.lower() or "studio" in exe.name.lower() or "igor" in exe.name.lower():
                            out.append(exe)
        except OSError:
            pass

    resolved = []
    seen = set()
    for item in out:
        try:
            res = item.resolve()
            if res not in seen:
                seen.add(res)
                resolved.append(res)
        except OSError:
            pass
    return resolved

def _runtime_roots() -> List[Path]:
    """Discover runtime cache directories and ProgramData runtimes."""
    roots: List[Path] = []
    for env_name in ("PROGRAMDATA", "LOCALAPPDATA", "APPDATA"):
        val = os.environ.get(env_name)
        if val:
            p = Path(val)
            roots.extend([
                p / "GameMakerStudio2" / "Cache" / "runtimes",
                p / "GameMaker" / "Cache" / "runtimes",
                p / "GameMakerStudio2-LTS2026" / "Cache" / "runtimes",
                p / "GameMakerStudio2",
                p / "GameMaker",
            ])
    
    # Do not append hard-coded C:\ locations here.  The environment-derived
    # roots above cover standard Windows installs and preserve test isolation.
            
    for ide in _registry_ide_candidates():
        base = ide if ide.is_dir() else ide.parent
        roots.append(base / "runtimes")
        roots.append(base / "Runtime")
        roots.append(base.parent / "runtimes")
        roots.append(base.parent.parent / "GameMakerStudio2" / "Cache" / "runtimes")
        
    return [r for r in roots if r.exists()]

def _find_igor() -> Tuple[Optional[Path], Optional[Path]]:
    """Locate Igor.exe and its parent runtime root.

    Explicit paths are checked first so service deployments and isolated test
    workers can point at a known GameMaker installation deterministically.
    """
    explicit_igor = os.environ.get("AI_GRADER_GAMEMAKER_IGOR")
    if explicit_igor:
        igor = Path(explicit_igor).expanduser()
        if igor.is_file():
            explicit_runtime = os.environ.get("AI_GRADER_GAMEMAKER_RUNTIME_ROOT")
            runtime = Path(explicit_runtime).expanduser() if explicit_runtime else _runtime_root_for_igor(igor)
            if runtime is not None and runtime.exists():
                return igor.resolve(), runtime.resolve()

    candidates = []
    
    for cmd in ("Igor.exe", "igor"):
        found = shutil.which(cmd)
        if found:
            p = Path(found)
            candidates.append((p, _runtime_root_for_igor(p)))
            
    for rroot in _runtime_roots():
        try:
            for igor in rroot.glob("**/Igor.exe"):
                candidates.append((igor, _runtime_root_for_igor(igor)))
        except OSError:
            pass
            
    for ide in _registry_ide_candidates():
        base = ide if ide.is_dir() else ide.parent
        try:
            for igor in base.glob("**/Igor.exe"):
                candidates.append((igor, _runtime_root_for_igor(igor)))
        except OSError:
            pass

    if not candidates:
        return None, None
        
    best_igor, best_runtime = max(candidates, key=lambda pair: (pair[0].exists(), str(pair[1] or "")))
    return best_igor.resolve(), (best_runtime.resolve() if best_runtime else None)

def _runtime_root_for_igor(igor: Path) -> Optional[Path]:
    curr = igor.parent
    for _ in range(5):
        if curr.name.lower().startswith("runtime-") or (curr / "bin" / "Igor.exe").exists() or (curr / "lib").exists():
            return curr
        curr = curr.parent
    return igor.parent.parent if igor.parent.name.lower() == "bin" else igor.parent

def discover_gamemaker_toolchain() -> GameMakerToolchain:
    ide_candidates = _registry_ide_candidates()
    ide_path: Optional[Path] = None
    
    for c in ide_candidates:
        if c.is_file() and c.suffix.lower() == ".exe" and not "igor" in c.name.lower() and not "uninstall" in c.name.lower():
            ide_path = c
            break
    if not ide_path and ide_candidates:
        for c in ide_candidates:
            if c.is_dir():
                exes = list(c.glob("*.exe"))
                if exes:
                    ide_path = exes[0]
                    break
        if not ide_path:
            ide_path = ide_candidates[0] if ide_candidates[0].is_file() else None

    igor_path, runtime_root = _find_igor()
    
    # Auto-bootstrap / fallback for runtime if IDE is found but Igor is not indexed yet:
    # Scan standard ProgramData or AppData cache for any available runtime version
    if ide_path and not igor_path:
        for rroot in _runtime_roots():
            try:
                for sub in rroot.glob("runtime-*"):
                    pot = sub / "bin" / "igor" / "windows" / "x64" / "Igor.exe"
                    if not pot.exists():
                        pot = sub / "bin" / "Igor.exe"
                    if pot.exists():
                        igor_path = pot.resolve()
                        runtime_root = sub.resolve()
                        break
            except OSError:
                pass
            if igor_path:
                break

    return GameMakerToolchain(
        ide_path=ide_path.resolve() if ide_path and ide_path.exists() else None,
        igor_path=igor_path,
        runtime_root=runtime_root,
        user_folder=_find_user_folder(),
    )

def preflight_gamemaker_runtime_dependency(student_files: List[str]) -> dict:
    """Classify GameMaker submissions before grading.

    A submission with a runnable EXE is valid without a local IDE. A source-only
    submission (.yyp/.yyz/.gmx or a project directory) requires the local
    GameMaker toolchain so the worker can build/run it. The result deliberately
    exposes both ``gamemaker_detected`` and ``pause_reason`` for the UI.
    """
    tc = discover_gamemaker_toolchain()
    projects = []
    gamemaker_detected = False
    runnable_supplied = False
    source_supplied = False

    def _entry_paths(entry):
        if isinstance(entry, dict):
            values = list(entry.get("submission_paths") or [])
            if entry.get("path"):
                values.append(entry.get("path"))
            return [str(value) for value in values if value]
        if isinstance(entry, (str, Path)):
            return [str(entry)]
        return []

    for entry in student_files or []:
        paths = _entry_paths(entry)
        suffixes = {Path(path).suffix.lower() for path in paths}
        has_exe = ".exe" in suffixes
        has_source = bool(suffixes.intersection({".yyp", ".yyz", ".gmx", ".gmk", ".project"}))
        has_game_artifact = has_exe or has_source or ".win" in suffixes
        runnable_supplied = runnable_supplied or has_exe
        source_supplied = source_supplied or has_source
        gamemaker_detected = gamemaker_detected or has_game_artifact
        projects.append({
            "path": str(entry.get("path")) if isinstance(entry, dict) and entry.get("path") else (paths[0] if paths else None),
            "submission_paths": paths,
            "has_exe": has_exe,
            "source_project": has_source,
            "runnable_supplied": has_exe,
        })

    if runnable_supplied:
        return {
            "gamemaker_detected": True,
            "pause_required": False,
            "passed": True,
            "dependency": "gamemaker",
            "reason": "runnable_supplied",
            "pause_reason": None,
            "message_ar": "تم العثور على ملف EXE قابل للتشغيل؛ لا يلزم تثبيت GameMaker على هذا الحاسوب.",
            "projects": projects,
            "toolchain": tc.to_dict(),
            "download_url": "https://gamemaker.io/en/download",
        }

    if not source_supplied and gamemaker_detected:
        source_supplied = True

    if source_supplied:
        if not tc.installed:
            return {
                "gamemaker_detected": True,
                "pause_required": True,
                "passed": False,
                "dependency": "gamemaker",
                "reason": "gamemaker_not_installed",
                "pause_reason": "gamemaker_not_installed",
                "message_ar": "تم اكتشاف مشروع GameMaker المصدرّي، لكن لم يتم العثور على GameMaker على هذا الحاسوب. افتح GameMaker أو ثبّته ثم اضغط Complete.",
                "projects": projects,
                "toolchain": tc.to_dict(),
                "download_url": "https://gamemaker.io/en/download",
            }
        if not tc.ready:
            return {
                "gamemaker_detected": True,
                "pause_required": True,
                "passed": False,
                "dependency": "gamemaker",
                "reason": tc.reason,
                "pause_reason": tc.reason,
                "message_ar": "تم العثور على GameMaker، لكن Runtime/Igor غير جاهز. افتح GameMaker واتركه ينزّل Runtime ثم اضغط Complete.",
                "projects": projects,
                "toolchain": tc.to_dict(),
                "download_url": "https://gamemaker.io/en/download",
            }

        return {
            "gamemaker_detected": True,
            "pause_required": False,
            "passed": True,
            "dependency": "gamemaker",
            "reason": "gamemaker_ready",
            "pause_reason": None,
            "message_ar": "تم اكتشاف مشروع GameMaker وIDE وRuntime جاهزين؛ سيُبنى المشروع المصدرّي تلقائياً قبل التحقق.",
            "projects": projects,
            "toolchain": tc.to_dict(),
            "download_url": "https://gamemaker.io/en/download",
        }

    return {
        "gamemaker_detected": False,
        "pause_required": False,
        "passed": True,
        "dependency": "gamemaker",
        "reason": "not_a_gamemaker_submission",
        "pause_reason": None,
        "message_ar": "لم يتم اكتشاف ملفات GameMaker في هذه الدفعة؛ سيستمر التصحيح العام.",
        "projects": projects,
        "toolchain": tc.to_dict(),
        "download_url": "https://gamemaker.io/en/download",
    }

