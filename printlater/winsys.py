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


def open_in_bambu_studio(file: Path, configured: str = "") -> None:
    exe = find_bambu_studio(configured)
    if exe:
        subprocess.Popen([exe, str(file)], close_fds=True)
    elif IS_WIN:
        os.startfile(str(file))  # noqa: S606 - default app for .3mf
    else:
        raise RuntimeError("Bambu Studio not found")
