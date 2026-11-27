"""The 'Print later' dialog opened from the Explorer context menu."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

from . import autosend, core, project, sliced, winsys
from .config import Settings, load_state, save_state
from .text import tr


def _dur(sec: int | None) -> str:
    if not sec:
        return "?"
    h, m = divmod(sec // 60, 60)
    return f"{h}h{m:02d}" if h else f"{m} min"


def connect_ha(settings: Settings, make_ha, L, warn):
    """Home Assistant link, or None when disabled. Raises when it is required but unreachable or a
    core entity is missing, unless continue_without_ha is set. Missing status/queue entities are
    skipped with a warning."""
    hac = settings.homeassistant
    if not hac.enabled:
        return None
    try:
        ha = make_ha()
        dropped = ha.check_entities()
        if dropped:
            warn(L("optional_missing", ents=", ".join(dropped)))
        return ha
    except Exception as e:  # noqa: BLE001
        if hac.continue_without_ha:
            warn(L("ha_fail", err=e))
            return None
        raise RuntimeError(L("ha_stop", err=e)) from e


def busy_message(ha, state: str, L, has_queue: bool) -> str:
    task = ha.task()
    msg = L("busy", state=state, task=f", {task}" if task and task not in ("unknown", "unavailable") else "")
    status, name, start = ha.current_plan()
    if status in ("planned", "waiting") and name:
        msg += "\n" + L("busy_plan", name=name, start=start[:16])
    if has_queue:
        msg += "\n\n" + L("queue_hint")
    return msg


def filament_lines(info: sliced.SlicedFile) -> list[sliced.Filament]:
    return [f for p in info.plates for f in p.filament_details]


def confirm_send(root, L, file_name: str, info: sliced.SlicedFile) -> str:
    """Modal check before the automatic send: shows file and filaments. Returns auto/manual/cancel."""
    answer = {"v": "cancel"}
    w = tk.Toplevel(root)
    w.title(L("confirm_title"))
    w.transient(root)
    w.resizable(False, False)
    w.attributes("-topmost", True)
    fr = ttk.Frame(w, padding=14)
    fr.grid()
    ttk.Label(fr, text=L("confirm_head"), font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(fr, text=file_name).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 8))
    row = 2
    for fil in filament_lines(info) or [sliced.Filament("?", "?", "")]:
        sw = tk.Canvas(fr, width=18, height=18, highlightthickness=1, highlightbackground="#888")
        if fil.color.startswith("#") and len(fil.color) == 7:
            sw.create_rectangle(0, 0, 20, 20, fill=fil.color, outline="")
        sw.grid(row=row, column=0, sticky="w", pady=2)
        grams = f", {fil.grams:.0f} g" if fil.grams else ""
        ttk.Label(fr, text=L("confirm_fil", slot=fil.slot, type=fil.type, color=fil.color or "?", grams=grams)).grid(
            row=row, column=1, columnspan=2, sticky="w", padx=(8, 0))
        row += 1
    ttk.Label(fr, text=L("confirm_note"), foreground="#555", wraplength=360, justify="left").grid(
        row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))
    bf = ttk.Frame(fr)
    bf.grid(row=row + 1, column=0, columnspan=3, sticky="e", pady=(12, 0))

    def pick(v):
        answer["v"] = v
        w.destroy()
    ttk.Button(bf, text=L("cancel"), command=lambda: pick("cancel")).pack(side="right")
    ttk.Button(bf, text=L("confirm_manual"), command=lambda: pick("manual")).pack(side="right", padx=6)
    ok = ttk.Button(bf, text=L("confirm_auto"), command=lambda: pick("auto"))
    ok.pack(side="right")
    ok.focus_set()
    w.protocol("WM_DELETE_WINDOW", lambda: pick("cancel"))
    w.grab_set()
    root.wait_window(w)
    return answer["v"]


def run(src: Path, settings: Settings, make_ha, target: datetime | None = None, queue_uid: str = "") -> None:
    """Planning dialog for a sliced .gcode.3mf or a saved project (.3mf). `target` pre-fills the time;
    `queue_uid` marks a queue item done once planned."""
    lang = winsys.ui_language(settings.language)
    L = lambda k, **kw: tr(lang, k, **kw)  # noqa: E731
    is_project = not project.is_sliced(src)
    info = None if is_project else sliced.read(src)
    plates = project.read_plates(src) if is_project else []
    target0 = target if target and target > datetime.now() + timedelta(minutes=2) else \
        core.default_target(settings.timing.default_time)
    hac = settings.homeassistant

    root = tk.Tk()
    root.title(L("title"))
    root.resizable(False, False)
    root.attributes("-topmost", True)
    f = ttk.Frame(root, padding=14)
    f.grid()
    r = 0
    ttk.Label(f, text=src.name, font=("Segoe UI", 10, "bold")).grid(row=r, column=0, columnspan=3, sticky="w")
    r += 1
    plate_v = tk.StringVar()
    if is_project:
        model = project.printer_model(src)
        ttk.Label(f, text=L("project_info", plates=len(plates), printer=model or "?"), foreground="#555").grid(
            row=r, column=0, columnspan=3, sticky="w", pady=(0, 8))
        r += 1
        if len(plates) > 1:
            ttk.Label(f, text=L("plate")).grid(row=r, column=0, sticky="w")
            cb = ttk.Combobox(f, textvariable=plate_v, values=[p.label() for p in plates], state="readonly", width=28)
            cb.grid(row=r, column=1, columnspan=2, sticky="w")
            r += 1
        plate_v.set(plates[0].label())
        if settings.printer_model and model and model != settings.printer_model:
            ttk.Label(f, text=L("wrong_printer", have=model, want=settings.printer_model), foreground="#a33",
                      wraplength=380, justify="left").grid(row=r, column=0, columnspan=3, sticky="w", pady=(0, 8))
            r += 1
    else:
        secs = sum(p.seconds or 0 for p in info.plates) or None
        grams = round(sum(p.grams or 0 for p in info.plates))
        mat = ", ".join(sorted({x.split()[0] for p in info.plates for x in p.filaments})) or ""
        ttk.Label(f, text=L("info", plates=len(info.plates), dur=_dur(secs), grams=grams, mat=mat),
                  foreground="#555").grid(row=r, column=0, columnspan=3, sticky="w", pady=(0, 8))
        r += 1

    ttk.Label(f, text=L("date")).grid(row=r, column=0, sticky="w")
    date_v = tk.StringVar(value=target0.strftime("%Y-%m-%d"))
    ttk.Entry(f, textvariable=date_v, width=12).grid(row=r, column=1, sticky="w")
    q = ttk.Frame(f)
    q.grid(row=r, column=2, sticky="w")
    today = datetime.now().date()
    ttk.Button(q, text=L("today"), width=9, command=lambda: date_v.set(today.isoformat())).pack(side="left")
    ttk.Button(q, text=L("tomorrow"), width=9,
               command=lambda: date_v.set((today + timedelta(days=1)).isoformat())).pack(side="left")
    r += 1
    ttk.Label(f, text=L("time")).grid(row=r, column=0, sticky="w", pady=(4, 0))
    time_v = tk.StringVar(value=target0.strftime("%H:%M"))
    ttk.Entry(f, textvariable=time_v, width=12).grid(row=r, column=1, sticky="w", pady=(4, 0))
    r += 1

    ttk.Label(f, text=L("meaning")).grid(row=r, column=0, columnspan=3, sticky="w", pady=(8, 0))
    r += 1
    meaning_v = tk.StringVar(value=settings.timing.meaning)
    ttk.Radiobutton(f, text=L("m_warmup"), value="warmup", variable=meaning_v).grid(row=r, column=0, columnspan=3, sticky="w")
    r += 1
    ttk.Radiobutton(f, text=L("m_printing") + f" (≈{settings.timing.prep_minutes:g} min)", value="printing",
                    variable=meaning_v).grid(row=r, column=0, columnspan=3, sticky="w")
    r += 1
    margin = f"{settings.timing.finish_margin_minutes:g}"
    total_s = None if is_project else core.print_seconds(info)
    finish_txt = L("m_finish_project", margin=margin) if is_project else L("m_finish", dur=_dur(total_s), margin=margin)
    finish_rb = ttk.Radiobutton(f, text=finish_txt, value="finish", variable=meaning_v)
    finish_rb.grid(row=r, column=0, columnspan=3, sticky="w")
    r += 1
    if not is_project and not total_s:
        finish_rb.state(["disabled"])
        if meaning_v.get() == "finish":
            meaning_v.set("warmup")
    ttk.Label(f, text=L("bed"), foreground="#a33").grid(row=r, column=0, columnspan=3, sticky="w", pady=(8, 0))
    r += 1
    auto_v = tk.BooleanVar(value=bool(load_state().get("auto_send", settings.auto_send)) and winsys.IS_WIN)
    auto_cb = ttk.Checkbutton(f, text=L("auto_send"), variable=auto_v)
    auto_cb.grid(row=r, column=0, columnspan=3, sticky="w", pady=(6, 0))
    if not winsys.IS_WIN:
        auto_cb.state(["disabled"])
    r += 1
    status = tk.StringVar(value="")
    ttk.Label(f, textvariable=status, wraplength=380, justify="left").grid(row=r, column=0, columnspan=3,
                                                                         sticky="w", pady=(8, 0))
    r += 1
    btns = ttk.Frame(f)
    btns.grid(row=r, column=0, columnspan=3, sticky="e", pady=(12, 0))
    cancel_b = ttk.Button(btns, text=L("cancel"), command=root.destroy)
    cancel_b.pack(side="right")
    plan_b = ttk.Button(btns, text=L("plan"))
    plan_b.pack(side="right", padx=6)
    queue_b = ttk.Button(btns, text=L("queue"))
    if hac.enabled and hac.queue_todo and not is_project:
        queue_b.pack(side="right")

    events: queue.Queue = queue.Queue()
    base_text = [""]  # status text before the late-send warning, so the warning replaces itself
    reply: queue.Queue = queue.Queue()  # answers from the main thread (filament confirmation)

    def connect():
        return connect_ha(settings, make_ha, L, lambda m: events.put(("status", m)))

    def busy_text(ha, state: str) -> str:
        return busy_message(ha, state, L, bool(hac.queue_todo))

    def chosen_plate():
        label = plate_v.get()
        return next((p for p in plates if p.label() == label), plates[0])

    def worker(target: datetime, meaning: str, auto: bool, plate):
        try:
            ha = connect()
            if ha:
                busy = ha.printer_busy()
                if busy:
                    events.put(("error", busy_text(ha, busy)))
                    return
                try:
                    ha.ensure_printer_on(lambda m: events.put(("status", L("power"))))
                except Exception as e:  # noqa: BLE001
                    events.put(("error", L("offline", err=e)))
                    return
            file = src
            if is_project:
                project.check_printer(src, settings.printer_model)
                events.put(("status", L("slicing", plate=plate.label())))
                dest = Path(settings.output_dir) if settings.output_dir else src.parent
                file = project.slice_project(src, plate, len(plates),
                                             winsys.find_bambu_studio(settings.bambu_studio) or "", dest)
            file_info = sliced.read(file)
            if auto:
                events.put(("confirm", (file.name, file_info)))
                choice = reply.get()
                if choice == "cancel":
                    events.put(("status", L("cancelled")))
                    events.put(("reenable", None))
                    return
                auto = choice == "auto"
            plan = core.make_plan(file, target, settings, meaning=meaning)
            planned_start = plan.warmup_planned
            fin_total = core.print_seconds(file_info)
            if ha:
                ha.set_plan("planned", plan.job_name, planned_start)
            was_open = winsys.studio_running()
            old_windows = frozenset(winsys.find_windows(plan.job_name))  # e.g. an earlier attempt
            winsys.open_in_bambu_studio(plan.output, settings.bambu_studio)
            msg = L("made", file=plan.output.name)
            if was_open:
                msg += "\n" + L("studio_open", name=plan.job_name)
            msg += "\n" + (L("auto_sending") if auto else L("send_now", lead=settings.timing.send_lead_seconds))
            events.put(("status", msg))
            events.put(("untop", None))
            threading.Thread(target=winsys.bring_to_front, args=(plan.job_name,),
                             kwargs={"exclude": old_windows}, daemon=True).start()
            if auto:
                def do_send():
                    res = autosend.send_via_studio(plan.job_name, old_windows)
                    if res.ok:
                        events.put(("status2", L("auto_sent")))
                        return
                    detail = ("\n" + "\n".join(res.messages)) if res.messages else ""
                    reason = L("r_" + res.reason)
                    events.put(("status2", L("auto_failed", reason=reason) + detail))
                    if ha:
                        ha.notify(L("auto_failed_notify", name=plan.job_name, reason=reason) + detail)
                threading.Thread(target=do_send, daemon=True).start()
            if not ha:
                events.put(("done", None))
                return
            events.put(("status2", L("waiting")))
            last_warn = [0]

            def tick(elapsed: float) -> None:
                minutes = int(elapsed // 60)
                if minutes >= 2 and minutes > last_warn[0]:
                    last_warn[0] = minutes
                    if_now = datetime.now() + timedelta(seconds=plan.transfer_s + plan.delay_s)
                    events.put(("late", L("late", min=minutes, name=plan.job_name,
                                          start=f"{if_now:%H:%M}", planned=f"{planned_start:%H:%M}")))

            running = ha.wait_for_job(plan.job_name, on_tick=tick)
            if running is None:
                try:
                    ha.set_plan("failed")
                except Exception:  # noqa: BLE001
                    pass
                events.put(("done", L("no_confirm", start=f"{planned_start:%H:%M}")))
                return
            actual = plan.warmup_at(running)
            try:
                ha.set_plan("waiting", plan.job_name, actual)
                ha.queue_done(queue_uid)
            except Exception:  # noqa: BLE001
                pass
            dev = (actual - planned_start).total_seconds()
            dev_txt = ""
            if abs(dev) >= 30:
                m, s_ = divmod(int(abs(dev)), 60)
                dev_txt = L("dev", sign="+" if dev > 0 else "-", m=m, s=s_)
            done = L("accepted", run=f"{running:%H:%M:%S}", start=f"{actual:%H:%M:%S}", dev=dev_txt)
            if plan.meaning == "finish" and fin_total:
                done += "\n" + L("finish_eta", eta=f"{actual + timedelta(seconds=fin_total):%H:%M}")
            events.put(("done", done))
        except Exception as e:  # noqa: BLE001
            events.put(("error", str(e)))

    def queue_worker(target: datetime):
        try:
            ha = connect()
            if not ha:
                raise RuntimeError(L("ha_stop", err="-"))
            name = src.name.removesuffix(".3mf").removesuffix(".gcode")
            wish = target if target > datetime.now() else None
            if not queue_uid:
                ha.queue_add(name, str(src), wish)
            events.put(("done", L("queued", name=name,
                                  wish=L("wish", when=f"{wish:%d-%m %H:%M}") if wish else L("asap"))))
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
                    base_text[0] = status.get()
                elif kind == "late":
                    status.set(base_text[0] + "\n\n" + msg)
                elif kind == "untop":
                    root.attributes("-topmost", False)
                elif kind == "confirm":
                    reply.put(confirm_send(root, L, *msg))
                elif kind == "error":
                    messagebox.showerror(L("err"), msg, parent=root)
                    plan_b.state(["!disabled"])
                    queue_b.state(["!disabled"])
                elif kind == "reenable":
                    plan_b.state(["!disabled"])
                    queue_b.state(["!disabled"])
                elif kind == "done":
                    if msg:
                        first = status.get().split("\n\n")[0]
                        status.set(first + "\n\n" + msg if first else msg)
                    cancel_b.configure(text=L("close"))
        except queue.Empty:
            pass
        root.after(300, poll)

    def start(fn, *extra):
        try:
            target = core.parse_when(date_v.get(), time_v.get())
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(L("err"), str(e), parent=root)
            return
        plan_b.state(["disabled"])
        queue_b.state(["disabled"])
        threading.Thread(target=fn, args=(target, *extra), daemon=True).start()

    def on_plan():
        save_state(auto_send=bool(auto_v.get()))
        start(worker, meaning_v.get(), bool(auto_v.get()), chosen_plate() if is_project else None)

    plan_b.configure(command=on_plan)
    queue_b.configure(command=lambda: start(queue_worker))
    root.bind("<Escape>", lambda _e: root.destroy())
    root.after(300, poll)
    root.mainloop()
