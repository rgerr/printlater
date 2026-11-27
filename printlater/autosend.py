"""Optional automatic send: press Print plate and Send in the Bambu Studio window that holds the
delayed file, the way you would yourself. Bambu Studio does the sending; PrintLater only clicks.

Buttons are found by their label (Bambu Studio gives each button its own window with the label as
window text), not by screen position, and clicks are sent as window messages, so Studio does not
need to be in front. When anything looks off the send dialog is left open for you."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import winsys

PRINT_LABELS = ("Printplaat", "Print plate")
SEND_LABELS = ("Versturen", "Send")
DIALOG_CLASS = "#32770"


@dataclass
class SendResult:
    ok: bool
    reason: str = ""          # code: not_windows, no_window, no_print_button, no_dialog, send_disabled, still_open
    messages: list[str] = field(default_factory=list)


def messages_from(texts: list[str]) -> list[str]:
    """Sentences shown in the send dialog (warnings such as 'The printer is busy ...'), without the
    short labels and values that are always there (Printer, Filament, 2h47m, 105,53 g ...)."""
    out = []
    for t in texts:
        t = " ".join(t.split())
        if len(t.split()) >= 4 and not t.endswith(("...", "…")) and t not in out:  # skip cut-off labels
            out.append(t)
    return out


def send_via_studio(job_title: str, exclude: frozenset[int] = frozenset(), *, load_timeout: float = 180,
                    dialog_timeout: float = 20, enable_timeout: float = 60, close_timeout: float = 300,
                    poll: float = 0.5, log=lambda _m: None) -> SendResult:
    if not winsys.IS_WIN:
        return SendResult(False, "not_windows")
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    def visible(h):
        return bool(user32.IsWindow(h) and user32.IsWindowVisible(h))

    def enabled(h):
        return bool(user32.IsWindowEnabled(h))

    def pid_of(h):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        return pid.value

    def children(root):
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(h, _l):
            found.append(h)
            return True
        user32.EnumChildWindows(root, cb, 0)
        return found

    def child_with(root, labels):
        for h in children(root):
            if visible(h) and winsys.window_text(h) in labels:
                return h
        return None

    def dialogs_of(pid):
        tops = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(h, _l):
            if visible(h) and pid_of(h) == pid and winsys.window_class(h) == DIALOG_CLASS:
                tops.append(h)
            return True
        user32.EnumWindows(cb, 0)
        return set(tops)

    def click(h):
        r = wintypes.RECT()
        user32.GetClientRect(h, ctypes.byref(r))
        lp = ((r.bottom // 2) << 16) | (r.right // 2)
        user32.PostMessageW(h, 0x0201, 1, lp)  # WM_LBUTTONDOWN
        time.sleep(0.05)
        user32.PostMessageW(h, 0x0202, 0, lp)  # WM_LBUTTONUP

    def texts_in(root):
        return [winsys.window_text(h) for h in children(root)
                if visible(h) and winsys.window_class(h) == "Static" and winsys.window_text(h)]

    def wait(cond, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            v = cond()
            if v:
                return v
            time.sleep(poll)
        return None

    # 1. the Studio window with the delayed file, loaded far enough to show an active Print plate
    main = wait(lambda: next((h for h in winsys.find_windows(job_title) if h not in exclude), None), load_timeout)
    if not main:
        return SendResult(False, "no_window")
    print_btn = wait(lambda: (lambda b: b if b and enabled(b) else None)(child_with(main, PRINT_LABELS)), load_timeout)
    if not print_btn:
        return SendResult(False, "no_print_button")
    log("Print plate")
    pid = pid_of(main)
    before = dialogs_of(pid)

    # 2. the send dialog
    click(print_btn)
    dialog = wait(lambda: next(iter(dialogs_of(pid) - before), None), dialog_timeout)
    if not dialog:
        return SendResult(False, "no_dialog")

    # 3. Send, once Studio enables it (it stays disabled while the printer is busy or unreachable)
    send_btn = wait(lambda: (lambda b: b if b and enabled(b) else None)(child_with(dialog, SEND_LABELS)), enable_timeout)
    msgs = messages_from(texts_in(dialog))
    if not send_btn:
        return SendResult(False, "send_disabled", msgs)
    log("Send")
    click(send_btn)

    # 4. Studio closes the dialog once the job is uploaded
    if wait(lambda: not visible(dialog), close_timeout):
        return SendResult(True, messages=msgs)
    return SendResult(False, "still_open", messages_from(texts_in(dialog)))
