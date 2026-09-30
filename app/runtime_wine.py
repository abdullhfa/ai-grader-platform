"""Linux/Wine backend for running Windows game executables.

Three responsibilities, all real (never "wine is installed, therefore it works"):

1. ``probe_wine_launcher`` — actually starts a throw-away Wine process on a
   virtual display and requires it to succeed.  Only then is the host said to be
   able to launch a Windows ``.exe``.
2. ``WineRuntime`` — an isolated Xvfb display + Wine prefix for one game run,
   with X11 screenshots (mss) and XTEST input (keys and mouse) through ctypes.
3. ``classify_wine_failure`` — separates a *platform* fault (Wine cannot start,
   no display, missing 32-bit runtime) from a *student* fault (the game itself
   crashed).  Only the latter can ever be read as a runtime failure.

No verification rules live here: it is only the launcher and the hands/eyes.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROBE_CACHE: Dict[str, Any] = {}
_ACTIVE: Optional["WineRuntime"] = None
_ACTIVE_LOCK = threading.Lock()

# Wine stderr fragments that mean "the launcher is broken", not "the game is".
_PLATFORM_FAULT_MARKERS = (
    "wine32 is missing",
    "could not load kernel32.dll",
    "wine: cannot find",
    "nodrv_createwindow",
    "no driver could be loaded",
    "cannot open display",
    "wine: failed to open",
    "wine: could not",
    "err:module:import_dll",
    # The game process died inside the emulator (typically no GPU/Vulkan under
    # Xvfb).  Under Wine this cannot be attributed to the student's game.
    "unhandled page fault",
    "unhandled exception",
    "starting debugger",
)

# X keysyms for the labels used by the verifier.
_KEYSYMS = {
    "W": 0x77, "A": 0x61, "S": 0x73, "D": 0x64,
    "SPACE": 0x20, "ENTER": 0xFF0D, "RETURN": 0xFF0D, "ESC": 0xFF1B,
    "UP": 0xFF52, "DOWN": 0xFF54, "LEFT": 0xFF51, "RIGHT": 0xFF53,
}


def shared_prefix_dir() -> Path:
    raw = os.environ.get("AI_GRADER_WINE_PREFIX")
    return Path(raw) if raw else Path(tempfile.gettempdir()) / "ai_grader_wine_prefix"


def wine_binary() -> Optional[str]:
    override = os.environ.get("AI_GRADER_WINE_BIN")
    if override and Path(override).is_file():
        return override
    for candidate in ("/usr/lib/wine/wine64", "/usr/lib/x86_64-linux-gnu/wine/wine64"):
        if Path(candidate).is_file():
            return candidate
    return shutil.which("wine64") or shutil.which("wine")


def classify_wine_failure(stderr_text: str) -> Optional[str]:
    """Return the matched platform-fault marker, or None if it looks like the game."""
    low = (stderr_text or "").lower()
    for marker in _PLATFORM_FAULT_MARKERS:
        if marker in low:
            return marker
    return None


def _free_display() -> str:
    for n in range(90, 140):
        if not Path(f"/tmp/.X11-unix/X{n}").exists() and not Path(f"/tmp/.X{n}-lock").exists():
            return f":{n}"
    return ":99"


class WineRuntime:
    """Xvfb + Wine prefix + X11 input/screenshot for one game run."""

    def __init__(self, *, screen: str = "1280x720x24") -> None:
        self.screen = screen
        self.display: Optional[str] = None
        self.prefix: Optional[Path] = None
        self._xvfb: Optional[subprocess.Popen] = None
        self._proc: Optional[subprocess.Popen] = None
        self._stderr_path: Optional[Path] = None
        self._x11 = None
        self._xtst = None
        self._dpy = None
        self.start_error: Optional[str] = None

    # ── lifecycle ────────────────────────────────────────────────────────────
    def __enter__(self) -> "WineRuntime":
        global _ACTIVE
        try:
            self._start_display()
            self.prefix = shared_prefix_dir()
            self.prefix.mkdir(parents=True, exist_ok=True)
            self._open_x()
        except Exception as exc:  # noqa: BLE001 - reported as a platform fault
            self.start_error = f"{type(exc).__name__}: {exc}"
            self.close()
            return self
        with _ACTIVE_LOCK:
            _ACTIVE = self
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    @property
    def ok(self) -> bool:
        return self.start_error is None and self._dpy is not None

    def _start_display(self) -> None:
        if not shutil.which("Xvfb"):
            raise RuntimeError("Xvfb is not installed")
        self.display = _free_display()
        self._xvfb = subprocess.Popen(
            ["Xvfb", self.display, "-screen", "0", self.screen, "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        sock = Path(f"/tmp/.X11-unix/X{self.display[1:]}")
        deadline = time.time() + 8
        while time.time() < deadline and not sock.exists():
            if self._xvfb.poll() is not None:
                raise RuntimeError("Xvfb exited immediately")
            time.sleep(0.1)
        if not sock.exists():
            raise RuntimeError("Xvfb did not create its socket")

    def _open_x(self) -> None:
        x11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
        xtst = ctypes.CDLL(ctypes.util.find_library("Xtst") or "libXtst.so.6")
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XKeysymToKeycode.restype = ctypes.c_ubyte
        x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        dpy = x11.XOpenDisplay(self.display.encode())
        if not dpy:
            raise RuntimeError("cannot open the virtual display")
        self._x11, self._xtst, self._dpy = x11, xtst, ctypes.c_void_p(dpy)

    def env(self) -> Dict[str, str]:
        env = dict(os.environ)
        env.update(
            DISPLAY=self.display or "",
            WINEPREFIX=str(self.prefix or ""),
            WINEARCH="win64",
            WINEDEBUG="err+all,fixme-all",
            WINEDLLOVERRIDES="mscoree,mshtml=",
        )
        return env

    def launch(self, exe: Path, *, cwd: Path) -> subprocess.Popen:
        binary = wine_binary()
        if not binary:
            raise RuntimeError("wine is not installed")
        self._stderr_path = (self.prefix or Path(tempfile.gettempdir())) / "wine_stderr.log"
        err = open(self._stderr_path, "wb")
        self._proc = subprocess.Popen(
            [binary, str(exe)],
            cwd=str(cwd),
            env=self.env(),
            stdout=subprocess.DEVNULL,
            stderr=err,
            start_new_session=True,
        )
        return self._proc

    def stderr_text(self) -> str:
        try:
            return (self._stderr_path.read_text("utf-8", "replace") if self._stderr_path else "")[-6000:]
        except OSError:
            return ""

    def close(self) -> None:
        global _ACTIVE
        with _ACTIVE_LOCK:
            if _ACTIVE is self:
                _ACTIVE = None
        if self._proc and self._proc.poll() is None:
            try:
                os.killpg(self._proc.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        if self.prefix and self.display:
            try:
                subprocess.run(
                    ["wineserver", "-k"], env=self.env(), timeout=15,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
        if self._dpy is not None and self._x11 is not None:
            try:
                self._x11.XCloseDisplay(self._dpy)
            except Exception:
                pass
            self._dpy = None
        if self._xvfb and self._xvfb.poll() is None:
            self._xvfb.terminate()
            try:
                self._xvfb.wait(5)
            except subprocess.TimeoutExpired:
                self._xvfb.kill()
        # The prefix is a reusable runtime environment (not a generated build):
        # it is kept so later runs skip the slow first-run initialisation.
        self.prefix = None

    # ── eyes ────────────────────────────────────────────────────────────────
    def grab(self):
        """PIL image of the virtual screen (the game is the only window on it)."""
        import mss
        from PIL import Image

        prev = os.environ.get("DISPLAY")
        os.environ["DISPLAY"] = self.display or ""
        try:
            with mss.mss() as sct:
                shot = sct.grab(sct.monitors[0])
                return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        finally:
            if prev is None:
                os.environ.pop("DISPLAY", None)
            else:
                os.environ["DISPLAY"] = prev

    # ── hands (XTEST) ───────────────────────────────────────────────────────
    def _keycode(self, label: str) -> int:
        sym = _KEYSYMS.get(label.upper())
        if sym is None:
            return 0
        return int(self._x11.XKeysymToKeycode(self._dpy, sym))

    def _flush(self) -> None:
        self._x11.XFlush(self._dpy)

    def key_down(self, label: str) -> bool:
        code = self._keycode(label)
        if not code:
            return False
        self._xtst.XTestFakeKeyEvent(self._dpy, code, 1, 0)
        self._flush()
        return True

    def key_up(self, label: str) -> bool:
        code = self._keycode(label)
        if not code:
            return False
        self._xtst.XTestFakeKeyEvent(self._dpy, code, 0, 0)
        self._flush()
        return True

    def key_hold(self, label: str, seconds: float) -> bool:
        if not self.key_down(label):
            return False
        time.sleep(max(seconds, 0.05))
        return self.key_up(label)

    def click(self, x: int, y: int) -> bool:
        self._xtst.XTestFakeMotionEvent(self._dpy, -1, int(x), int(y), 0)
        self._flush()
        time.sleep(0.05)
        self._xtst.XTestFakeButtonEvent(self._dpy, 1, 1, 0)
        self._xtst.XTestFakeButtonEvent(self._dpy, 1, 0, 0)
        self._flush()
        return True

    def screen_size(self) -> Tuple[int, int]:
        try:
            w, h, _ = self.screen.split("x")
            return int(w), int(h)
        except ValueError:
            return 1280, 720


def active_runtime() -> Optional[WineRuntime]:
    """The Wine run currently in progress (used by capture and input helpers)."""
    with _ACTIVE_LOCK:
        return _ACTIVE if _ACTIVE is not None and _ACTIVE.ok else None


# ── launcher probe ──────────────────────────────────────────────────────────
def probe_wine_launcher(*, force: bool = False, timeout: int = 90) -> Dict[str, Any]:
    """Prove Wine can really start a Windows process here (cached).

    ``{"ok": bool, "reason": str}``.  Installed-but-broken Wine is ``ok: False``.
    """
    if not force and "result" in _PROBE_CACHE:
        return _PROBE_CACHE["result"]

    def done(ok: bool, reason: str) -> Dict[str, Any]:
        result = {"ok": ok, "reason": reason}
        _PROBE_CACHE["result"] = result
        return result

    override = os.environ.get("AI_GRADER_WINE_PROBE", "").strip().lower()
    if override in ("0", "off", "false"):
        return done(False, "wine launching disabled (AI_GRADER_WINE_PROBE=0)")
    binary = wine_binary()
    if not binary:
        return done(False, "wine is not installed")
    with WineRuntime() as rt:
        if not rt.ok:
            return done(False, f"virtual display unavailable: {rt.start_error}")
        try:
            proc = subprocess.run(
                [binary, "cmd", "/c", "exit", "0"],
                env=rt.env(), timeout=timeout,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
        except subprocess.TimeoutExpired:
            return done(False, "wine probe timed out")
        except OSError as exc:
            return done(False, f"wine could not be executed: {exc}")
        stderr = (proc.stderr or b"").decode("utf-8", "replace")
        marker = classify_wine_failure(stderr)
        if proc.returncode != 0 or marker:
            tail = " ".join(stderr.strip().splitlines()[-2:])[:200]
            return done(False, f"wine cannot start a Windows process ({marker or 'exit %d' % proc.returncode}): {tail}")
    return done(True, "wine launched a Windows process")


def reset_probe_cache() -> None:
    _PROBE_CACHE.clear()
