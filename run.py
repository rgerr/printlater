"""PrintLater: start a Bambu Lab print at a chosen time, without extra hardware or firmware changes.

Usage:
  run.py plan <file.gcode.3mf>                     open the dialog (also via right-click)
  run.py make <file.gcode.3mf> --at "YYYY-MM-DD HH:MM" [--printing]
                                                          only write the delayed file
  run.py set-token | check | install-menu | uninstall-menu

The packaged PrintLater.exe takes the same commands. It has no console window, so text
output goes to printlater.log in the settings folder, and set-token, check and running it
without a command use small dialog windows instead.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime
from pathlib import Path

from printlater import __version__, core, winsys
from printlater.config import config_path, data_dir, load
from printlater.ha import HA, save_token
from printlater.text import tr

HAS_CONSOLE = sys.stdout is not None


def _out(msg: str) -> None:
    """Print, or append to printlater.log when there is no console (packaged exe)."""
    if HAS_CONSOLE:
        print(msg)
        return
    try:
        with open(data_dir() / "printlater.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


def _tk():
    import tkinter as tk
    r = tk.Tk()
    r.withdraw()
    return r


def _box(msg: str, error: bool = False) -> None:
    try:
        from tkinter import messagebox
        r = _tk()
        (messagebox.showerror if error else messagebox.showinfo)("PrintLater", msg)
        r.destroy()
    except Exception:  # noqa: BLE001
        _out(msg)


def _ask_token(lang: str) -> str:
    if HAS_CONSOLE:
        return getpass.getpass(tr(lang, "token_prompt") + " ")
    from tkinter import simpledialog
    r = _tk()
    try:
        return simpledialog.askstring("PrintLater", tr(lang, "token_prompt"), show="*", parent=r) or ""
    finally:
        r.destroy()


def _check(settings) -> str:
    lines = [f"PrintLater {__version__}",
             f"Config: {config_path()} ({'found' if config_path().exists() else 'not found, using defaults'})",
             f"Bambu Studio: {winsys.find_bambu_studio(settings.bambu_studio) or 'not found (default .3mf app is used)'}"]
    if settings.homeassistant.enabled:
        ha = HA(settings.homeassistant)
        c = settings.homeassistant
        for ent in (c.plug, c.online, c.print_status, c.task_name, c.planned_flag, c.planned_start):
            if ent:
                lines.append(f"  {ent}: {ha.value(ent)}")
    else:
        lines.append("Home Assistant: disabled")
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    p = argparse.ArgumentParser(prog="PrintLater", description=f"PrintLater {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("plan"); a.add_argument("file")
    m = sub.add_parser("make"); m.add_argument("file"); m.add_argument("--at", required=True)
    m.add_argument("--printing", action="store_true", help="time means: first layer starts")
    for name in ("set-token", "check", "install-menu", "uninstall-menu"):
        sub.add_parser(name)

    if not argv and not HAS_CONSOLE:  # exe started without a command, e.g. from the Start menu
        _box(tr(winsys.ui_language(), "about", ver=__version__, cfg=config_path()))
        return 0
    try:
        args = p.parse_args(argv)
    except SystemExit as e:
        if not HAS_CONSOLE:
            _out(f"invalid command line: {argv}")
        return int(e.code or 0)

    interactive = args.cmd == "plan" or (not HAS_CONSOLE and args.cmd in ("set-token", "check"))
    try:
        settings = load()
        lang = winsys.ui_language(settings.language)
        if args.cmd == "plan":
            from printlater.gui import run
            run(Path(args.file).resolve(), settings, lambda: HA(settings.homeassistant))
            return 0
        if args.cmd == "make":
            d, t = args.at.split(" ", 1)
            plan = core.make_plan(Path(args.file).resolve(), core.parse_when(d, t), settings,
                                  meaning="printing" if args.printing else None)
            _out(f"{plan.output}\ndelay {plan.delay_s} s; send it within about "
                 f"{settings.timing.send_lead_seconds} s from now")
            return 0
        if args.cmd == "set-token":
            token = _ask_token(lang).strip()
            if not token:
                return 1
            save_token(token)
            (_out if HAS_CONSOLE else _box)(tr(lang, "token_saved"))
            return 0
        if args.cmd == "check":
            (_out if HAS_CONSOLE else _box)(_check(settings))
            return 0
        if args.cmd == "install-menu":
            winsys.install_context_menu(tr(lang, "menu"))
            _out("Context menu added for .3mf files.")
            return 0
        if args.cmd == "uninstall-menu":
            winsys.uninstall_context_menu()
            _out("Context menu removed.")
            return 0
    except Exception as e:  # noqa: BLE001 - no console when started from Explorer
        msg = f"{type(e).__name__}: {e}"
        _out(msg)
        if interactive:
            _box(msg, error=True)
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
