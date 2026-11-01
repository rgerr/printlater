"""The 'Print later' dialog opened from the Explorer context menu."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

from . import core, sliced, winsys
from .config import Settings
from .text import tr


def _dur(sec: int | None) -> str:
    if not sec:
        return "?"
    h, m = divmod(sec // 60, 60)
    return f"{h}h{m:02d}" if h else f"{m} min"


def run(src: Path, settings: Settings, make_ha) -> None:
    lang = winsys.ui_language(settings.language)
    L = lambda k, **kw: tr(lang, k, **kw)  # noqa: E731
    info = sliced.read(src)
    target0 = core.default_target(settings.timing.default_time)

    root = tk.Tk()
    root.title(L("title"))
    root.resizable(False, False)
    root.attributes("-topmost", True)
    f = ttk.Frame(root, padding=14)
    f.grid()
    ttk.Label(f, text=src.name, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
    secs = sum(p.seconds or 0 for p in info.plates) or None
    grams = round(sum(p.grams or 0 for p in info.plates))
    mat = ", ".join(sorted({x.split()[0] for p in info.plates for x in p.filaments})) or ""
    ttk.Label(f, text=L("info", plates=len(info.plates), dur=_dur(secs), grams=grams, mat=mat),
              foreground="#555").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 8))

    ttk.Label(f, text=L("date")).grid(row=2, column=0, sticky="w")
    date_v = tk.StringVar(value=target0.strftime("%Y-%m-%d"))
    ttk.Entry(f, textvariable=date_v, width=12).grid(row=2, column=1, sticky="w")
    q = ttk.Frame(f)
    q.grid(row=2, column=2, sticky="w")
    today = datetime.now().date()
    ttk.Button(q, text=L("today"), width=9, command=lambda: date_v.set(today.isoformat())).pack(side="left")
    ttk.Button(q, text=L("tomorrow"), width=9,
               command=lambda: date_v.set((today + timedelta(days=1)).isoformat())).pack(side="left")
    ttk.Label(f, text=L("time")).grid(row=3, column=0, sticky="w", pady=(4, 0))
    time_v = tk.StringVar(value=target0.strftime("%H:%M"))
    ttk.Entry(f, textvariable=time_v, width=12).grid(row=3, column=1, sticky="w", pady=(4, 0))

    ttk.Label(f, text=L("meaning")).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
    meaning_v = tk.StringVar(value=settings.timing.meaning)
    ttk.Radiobutton(f, text=L("m_warmup"), value="warmup", variable=meaning_v).grid(row=5, column=0, columnspan=3, sticky="w")
    ttk.Radiobutton(f, text=L("m_printing") + f" (≈{settings.timing.prep_minutes:g} min)", value="printing",
                    variable=meaning_v).grid(row=6, column=0, columnspan=3, sticky="w")
    ttk.Label(f, text=L("bed"), foreground="#a33").grid(row=7, column=0, columnspan=3, sticky="w", pady=(8, 0))
    status = tk.StringVar(value="")
    ttk.Label(f, textvariable=status, wraplength=380, justify="left").grid(row=8, column=0, columnspan=3,
                                                                         sticky="w", pady=(8, 0))
    btns = ttk.Frame(f)
    btns.grid(row=9, column=0, columnspan=3, sticky="e", pady=(12, 0))
    cancel_b = ttk.Button(btns, text=L("cancel"), command=root.destroy)
    cancel_b.pack(side="right")
    plan_b = ttk.Button(btns, text=L("plan"))
    plan_b.pack(side="right", padx=6)

    events: queue.Queue = queue.Queue()

    def worker(target: datetime, meaning: str):
        ha = None
        try:
            if settings.homeassistant.enabled:
                try:
                    ha = make_ha()
                    busy = ha.printer_busy()
                    if busy:
                        events.put(("error", L("busy", state=busy)))
                        return
                    ha.ensure_printer_on(lambda m: events.put(("status", L("power"))))
                except Exception as e:  # noqa: BLE001
                    events.put(("status", L("ha_fail", err=e)))
                    ha = None
            plan = core.make_plan(src, target, settings, meaning=meaning)
            planned_start = target - timedelta(seconds=plan.prep_s(settings))
            if ha:
                try:
                    ha.record_plan(planned_start)
                except Exception:  # noqa: BLE001
                    pass
            winsys.open_in_bambu_studio(plan.output, settings.bambu_studio)
            events.put(("status", L("made") + "\n" + L("send_now", lead=settings.timing.send_lead_seconds)))
            if not ha:
                events.put(("done", None))
                return
            events.put(("status2", L("waiting")))
            running = ha.wait_for_job(plan.job_name)
            if running is None:
                events.put(("done", L("no_confirm", start=f"{planned_start:%H:%M}")))
                return
            actual = plan.warmup_at(running)
            try:
                ha.record_plan(actual)
            except Exception:  # noqa: BLE001
                pass
            dev = (actual - planned_start).total_seconds()
            dev_txt = ""
            if abs(dev) >= 30:
                m, s = divmod(int(abs(dev)), 60)
                dev_txt = L("dev", sign="+" if dev > 0 else "-", m=m, s=s)
            events.put(("done", L("accepted", run=f"{running:%H:%M:%S}", start=f"{actual:%H:%M:%S}", dev=dev_txt)))
        except Exception as e:  # noqa: BLE001
            events.put(("error", str(e)))

    def poll():
        try:
            while True:
                kind, msg = events.get_nowait()
                if kind == "status":
                    status.set(msg)
                elif kind == "status2":
                    status.set(status.get() + "\n\n" + msg)
                elif kind == "error":
                    messagebox.showerror(L("err"), msg, parent=root)
                    plan_b.state(["!disabled"])
                elif kind == "done":
                    if msg:
                        status.set(status.get().split("\n\n")[0] + "\n\n" + msg)
                    cancel_b.configure(text=L("close"))
        except queue.Empty:
            pass
        root.after(300, poll)

    def on_plan():
        try:
            target = core.parse_when(date_v.get(), time_v.get())
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(L("err"), str(e), parent=root)
            return
        plan_b.state(["disabled"])
        threading.Thread(target=worker, args=(target, meaning_v.get()), daemon=True).start()

    plan_b.configure(command=on_plan)
    root.bind("<Escape>", lambda _e: root.destroy())
    root.after(300, poll)
    root.mainloop()
