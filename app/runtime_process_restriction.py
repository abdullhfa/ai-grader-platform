"""
Runtime process restriction — advisory guardrails for controlled EXE smoke tests.

Windows-focused: monitors child processes, flags suspicious spawns, kills process trees.
This is not a full sandbox; it reduces obvious risk during L4 observation.
"""
from __future__ import annotations

import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Set

SUSPICIOUS_PROCESS_NAMES = frozenset({
    "powershell.exe",
    "pwsh.exe",
    "cmd.exe",
    "wscript.exe",
    "cscript.exe",
    "mshta.exe",
    "rundll32.exe",
    "regsvr32.exe",
    "certutil.exe",
    "bitsadmin.exe",
    "curl.exe",
    "wget.exe",
})

RESTRICTION_MODE = "advisory_process_guard_v1"
WM_CLOSE = 0x0010
FILE_DIALOG_CLASS = "#32770"


def _normalize_name(name: str) -> str:
    return (name or "").strip().lower()


def is_suspicious_process(name: str) -> bool:
    return _normalize_name(name) in SUSPICIOUS_PROCESS_NAMES


def _windows_process_snapshot() -> List[Dict[str, Any]]:
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return []

    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.CHAR * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return []

    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    processes: List[Dict[str, Any]] = []
    try:
        if not kernel32.Process32First(snapshot, ctypes.byref(entry)):
            return processes
        while True:
            exe_name = entry.szExeFile.decode("mbcs", errors="replace")
            processes.append(
                {
                    "pid": int(entry.th32ProcessID),
                    "ppid": int(entry.th32ParentProcessID),
                    "name": exe_name,
                }
            )
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    return processes


def collect_process_tree(root_pid: int) -> List[Dict[str, Any]]:
    """Return root process and all descendant processes when available."""
    snapshot = _windows_process_snapshot()
    if not snapshot:
        return [{"pid": root_pid, "ppid": None, "name": "unknown"}]

    by_ppid: Dict[int, List[Dict[str, Any]]] = {}
    for proc in snapshot:
        by_ppid.setdefault(int(proc["ppid"]), []).append(proc)

    tree: List[Dict[str, Any]] = []
    stack = [root_pid]
    seen: Set[int] = set()
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        match = next((p for p in snapshot if int(p["pid"]) == pid), None)
        if match:
            tree.append(match)
        for child in by_ppid.get(pid, []):
            stack.append(int(child["pid"]))
    return tree


def scan_process_tree(root_pid: int) -> Dict[str, Any]:
    tree = collect_process_tree(root_pid)
    suspicious = [
        {
            "pid": p["pid"],
            "ppid": p["ppid"],
            "name": p["name"],
        }
        for p in tree
        if is_suspicious_process(str(p.get("name", "")))
    ]
    return {
        "process_count": len(tree),
        "process_tree": tree[:40],
        "suspicious_spawns": suspicious,
        "suspicious_spawn_detected": bool(suspicious),
    }


def kill_process_tree(root_pid: int, *, grace_seconds: float = 2.0) -> Dict[str, Any]:
    """Terminate a process tree on Windows; best-effort elsewhere."""
    result: Dict[str, Any] = {
        "root_pid": root_pid,
        "attempted": False,
        "method": "",
        "ok": False,
        "errors": [],
    }
    if root_pid <= 0:
        result["errors"].append("invalid_pid")
        return result

    if sys.platform == "win32":
        result["attempted"] = True
        try:
            proc = subprocess.run(
                ["taskkill", "/PID", str(root_pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=max(5, int(grace_seconds) + 3),
            )
            result["method"] = "taskkill_tree"
            result["ok"] = proc.returncode in (0, 128)
            if proc.stdout:
                result["stdout"] = proc.stdout[:500]
            if proc.stderr and not result["ok"]:
                result["errors"].append(proc.stderr[:500])
        except Exception as exc:
            result["errors"].append(str(exc))
        return result

    result["attempted"] = True
    result["method"] = "unsupported_platform"
    result["errors"].append("process_tree_kill_windows_only")
    return result


def dismiss_windows_file_dialogs(*, root_pid: Optional[int] = None) -> int:
    """
    Close modal Open/Save dialogs (#32770) spawned during EXE smoke tests.

    GameMaker exports without ``data.win`` can still pop a file picker on some
    builds; this is a safety net so batch grading never blocks on GUI dialogs.
    """
    if sys.platform != "win32":
        return 0

    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return 0

    allowed_pids: Set[int] = set()
    if root_pid and root_pid > 0:
        for proc in collect_process_tree(root_pid):
            allowed_pids.add(int(proc["pid"]))

    user32 = ctypes.windll.user32
    closed = 0

    def _is_open_dialog_title(title: str) -> bool:
        lowered = (title or "").strip().lower()
        if not lowered:
            return True
        markers = ("open", "save", "browse", "select", "choose", "فتح", "حفظ", "استعراض")
        return any(marker in lowered for marker in markers)

    def _callback(hwnd: int, _lparam: int) -> bool:
        nonlocal closed
        if not user32.IsWindowVisible(hwnd):
            return True
        class_name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_name, 256)
        if class_name.value != FILE_DIALOG_CLASS:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            title_buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title_buf, length + 1)
            title = title_buf.value
        if not _is_open_dialog_title(title):
            return True
        if allowed_pids:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in allowed_pids:
                return True
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        closed += 1
        return True

    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(_callback)
    user32.EnumWindows(enum_proc, 0)
    return closed


class RuntimeProcessGuard:
    """Lightweight in-loop process monitor for smoke tests."""

    def __init__(self, root_pid: int) -> None:
        self.root_pid = root_pid
        self.started_at = time.time()
        self.scans: List[Dict[str, Any]] = []
        self.suspicious_events: List[Dict[str, Any]] = []

    def scan_once(self) -> Dict[str, Any]:
        scan = scan_process_tree(self.root_pid)
        scan["scanned_at_sec"] = round(time.time() - self.started_at, 2)
        self.scans.append(scan)
        for item in scan.get("suspicious_spawns") or []:
            if item not in self.suspicious_events:
                self.suspicious_events.append(item)
        return scan

    def finalize(self) -> Dict[str, Any]:
        kill_result = kill_process_tree(self.root_pid)
        return build_restriction_report(
            root_pid=self.root_pid,
            scans=self.scans,
            suspicious_events=self.suspicious_events,
            kill_result=kill_result,
        )


def build_restriction_report(
    *,
    root_pid: int,
    scans: List[Dict[str, Any]],
    suspicious_events: List[Dict[str, Any]],
    kill_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    max_process_count = max((s.get("process_count") or 0 for s in scans), default=0)
    return {
        "restriction_mode": RESTRICTION_MODE,
        "root_pid": root_pid,
        "scan_count": len(scans),
        "max_process_count": max_process_count,
        "suspicious_spawn_detected": bool(suspicious_events),
        "suspicious_events": suspicious_events[:20],
        "process_tree_kill": kill_result or {},
        "authority_note_ar": (
            "Process restriction layer يقلّل المخاطر الواضحة فقط — "
            "ليس sandbox كاملًا ولا يضمن أمانًا مطلقًا."
        ),
        "network_isolated": False,
        "filesystem_isolated": False,
    }
