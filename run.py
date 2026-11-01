"""PrintLater: start a Bambu Lab print at a chosen time, without extra hardware or firmware changes.

Usage:
  run.py plan <file.gcode.3mf>                     open the dialog (also via right-click)
  run.py make <file.gcode.3mf> --at "YYYY-MM-DD HH:MM" [--printing]
                                                          only write the delayed file
  run.py set-token | check | install-menu | uninstall-menu
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from printlater import __version__, core, winsys
from printlater.config import config_path, load
from printlater.ha import HA, save_token
from printlater.text import tr


def _error_box(msg: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk(); r.withdraw()
        messagebox.showerror("PrintLater", msg)
        r.destroy()
    except Exception:  # noqa: BLE001
        print(msg, file=sys.stderr)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py", description=f"PrintLater {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("plan"); a.add_argument("file")
    m = sub.add_parser("make"); m.add_argument("file"); m.add_argument("--at", required=True)
    m.add_argument("--printing", action="store_true", help="time means: first layer starts")
    for name in ("set-token", "check", "install-menu", "uninstall-menu"):
        sub.add_parser(name)
    args = p.parse_args(argv)

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
            print(f"{plan.output}\ndelay {plan.delay_s} s; send it within about "
                  f"{settings.timing.send_lead_seconds} s from now")
            return 0
        if args.cmd == "set-token":
            save_token(getpass.getpass("Home Assistant long-lived access token: "))
            print("Token stored, encrypted for this Windows user (DPAPI).")
            return 0
        if args.cmd == "check":
            print(f"Config: {config_path()} ({'found' if config_path().exists() else 'not found, using defaults'})")
            print(f"Bambu Studio: {winsys.find_bambu_studio(settings.bambu_studio) or 'not found (default .3mf app is used)'}")
            if settings.homeassistant.enabled:
                ha = HA(settings.homeassistant)
                c = settings.homeassistant
                for ent in (c.plug, c.online, c.print_status, c.task_name, c.planned_flag, c.planned_start):
                    if ent:
                        print(f"  {ent}: {ha.value(ent)}")
            else:
                print("Home Assistant: disabled")
            return 0
        if args.cmd == "install-menu":
            winsys.install_context_menu(tr(lang, "menu"))
            print("Context menu added for .3mf files.")
            return 0
        if args.cmd == "uninstall-menu":
            winsys.uninstall_context_menu()
            print("Context menu removed.")
            return 0
    except Exception as e:  # noqa: BLE001 - pythonw has no console
        (_error_box if args.cmd == "plan" else print)(f"{type(e).__name__}: {e}")
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
