"""Windows helpers: DPAPI token storage, Explorer context menu, opening Bambu Studio."""
from __future__ import annotations

import base64
import ctypes
import locale
import os
import subprocess
import sys
from pathlib import Path

IS_WIN = sys.platform == "win32"

# ---------------------------------------------------------------- DPAPI (per-user encryption)
if IS_WIN:
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _crypt(fn, data: bytes) -> bytes:
        buf = ctypes.create_string_buffer(data, len(data))
        blob_in = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        out = _Blob()
        if not fn(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(out)):
            raise OSError("DPAPI call failed")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)

    def protect(data: bytes) -> bytes:
        return _crypt(ctypes.windll.crypt32.CryptProtectData, data)

    def unprotect(data: bytes) -> bytes:
        return _crypt(ctypes.windll.crypt32.CryptUnprotectData, data)
else:  # test-only fallback on non-Windows systems
    def protect(data: bytes) -> bytes:
        return b"TEST:" + base64.b64encode(data)

    def unprotect(data: bytes) -> bytes:
        return base64.b64decode(data.removeprefix(b"TEST:"))


# ---------------------------------------------------------------- language
def ui_language(setting: str = "") -> str:
    if setting in ("en", "nl"):
        return setting
    try:
        if IS_WIN:
            lang = locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), "")
        else:
            lang = locale.getlocale()[0] or ""
    except Exception:  # noqa: BLE001
        lang = ""
    return "nl" if lang.lower().startswith("nl") else "en"


# ---------------------------------------------------------------- context menu (current user, no admin)
MENU_KEY = r"Software\Classes\SystemFileAssociations\.3mf\shell\PrintLater"


FROZEN = bool(getattr(sys, "frozen", False))  # running as the packaged PrintLater.exe


def pythonw() -> str:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def main_script() -> str:
    return str(Path(__file__).resolve().parent.parent / "run.py")


def menu_command() -> tuple[str, str]:
    """(command line, icon) for the Explorer entry: the exe itself, or pythonw + run.py."""
    if FROZEN:
        return f'"{sys.executable}" plan "%1"', sys.executable
    return f'"{pythonw()}" "{main_script()}" plan "%1"', pythonw()


def install_context_menu(label: str) -> None:
    import winreg
    command, icon = menu_command()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, MENU_KEY) as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, label)
        winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, MENU_KEY + r"\command") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, command)


def uninstall_context_menu() -> None:
    import winreg
    for sub in (MENU_KEY + r"\command", MENU_KEY):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------- Bambu Studio
def find_bambu_studio(configured: str = "") -> str | None:
    if configured:
        return configured if Path(configured).exists() else None
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
        for sub in ("Bambu Studio", r"Programs\Bambu Studio"):
            p = Path(base, sub, "bambu-studio.exe")
            if p.exists():
                return str(p)
    return None


def studio_running() -> bool:
    """True when a Bambu Studio process is already running (Windows only)."""
    if not IS_WIN:
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq bambu-studio.exe", "/NH"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "bambu-studio.exe" in out.lower()


def window_text(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    n = user32.GetWindowTextLengthW(hwnd)
    if not n:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def find_windows(title_part: str) -> list[int]:
    """Handles of visible top-level windows whose title contains `title_part` (case-insensitive)."""
    if not IS_WIN or not title_part:
        return []
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found: list[int] = []
    key = title_part.lower()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd) and key in window_text(hwnd).lower():
            found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found


def bring_to_front(title_part: str, timeout_s: float = 90, poll_s: float = 1.0,
                   exclude: frozenset[int] = frozenset()) -> bool:
    """Wait for a window whose title contains `title_part`, then maximize it and bring it to the
    front, so Print plate is clicked in the window that holds the delayed file. Windows in
    `exclude` (already open before Studio was started) are skipped."""
    if not IS_WIN:
        return False
    import time
    user32 = ctypes.windll.user32
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        handles = [h for h in find_windows(title_part) if h not in exclude]
        if handles:
            hwnd = handles[0]
            user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
            user32.SetForegroundWindow(hwnd)
            return True
        time.sleep(poll_s)
    return False


def open_in_bambu_studio(file: Path, configured: str = "") -> None:
    exe = find_bambu_studio(configured)
    if exe:
        subprocess.Popen([exe, str(file)], close_fds=True)
    elif IS_WIN:
        os.startfile(str(file))  # noqa: S606 - default app for .3mf
    else:
        raise RuntimeError("Bambu Studio not found")
