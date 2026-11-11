from __future__ import annotations

import hashlib
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GCODE = ("; HEADER_BLOCK_START\n; total estimated time: 37m 37s\n; HEADER_BLOCK_END\n"
         "; curr_bed_type = Textured PEI Plate\n; EXECUTABLE_BLOCK_START\nM73 P0 R37\nM140 S55\nG28\n")


@pytest.fixture(autouse=True)
def appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))


def sliced_file(path: Path, plates=(1,)) -> Path:
    info = "<config>" + "".join(
        f'<plate><metadata key="index" value="{i}"/><metadata key="prediction" value="2257"/>'
        f'<metadata key="weight" value="13.79"/><metadata key="printer_model_id" value="N7"/>'
        f'<filament id="1" type="PETG" color="#FFFFFF"/></plate>' for i in plates) + "</config>"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("Metadata/slice_info.config", info)
        for i in plates:
            z.writestr(f"Metadata/plate_{i}.gcode", GCODE)
            z.writestr(f"Metadata/plate_{i}.gcode.md5", hashlib.md5(GCODE.encode()).hexdigest().upper())
    return path


# ------------------------------------------------------------------ delay block
def test_block_order_and_chunks():
    from printlater.delay import delay_block
    b = delay_block(200)
    waits = [l for l in b.splitlines() if l.startswith("M400")]
    assert waits == ["M400 S90", "M400 S90", "M400 S20"]
    assert b.index("M140 S0") < b.index("M18") < b.index("M400") < b.index("M17")


def test_apply_updates_md5_and_keeps_rest(tmp_path):
    from printlater.delay import apply_delay
    src = sliced_file(tmp_path / "a.gcode.3mf", plates=(1, 2))
    out = tmp_path / "b.gcode.3mf"
    info = apply_delay(src, out, 3600)
    assert info["steps"] == 40 and len(info["plates"]) == 2
    with zipfile.ZipFile(out) as z:
        for i in (1, 2):
            g = z.read(f"Metadata/plate_{i}.gcode").decode()
            assert z.read(f"Metadata/plate_{i}.gcode.md5").decode() == hashlib.md5(g.encode()).hexdigest().upper()
            assert g.index("EXECUTABLE_BLOCK_START") < g.index("PRINTLATER") < g.index("M73 P0 R37")
        assert z.read("[Content_Types].xml") == b"<Types/>"


def test_refuses_double_and_unsliced(tmp_path):
    from printlater.delay import DelayError, apply_delay
    src = sliced_file(tmp_path / "a.gcode.3mf")
    out = tmp_path / "b.gcode.3mf"
    apply_delay(src, out, 100)
    with pytest.raises(DelayError, match="already"):
        apply_delay(out, tmp_path / "c.gcode.3mf", 100)
    raw = tmp_path / "project.3mf"
    with zipfile.ZipFile(raw, "w") as z:
        z.writestr("3D/3dmodel.model", "<model/>")
    with pytest.raises(DelayError, match="No sliced"):
        apply_delay(raw, tmp_path / "d.gcode.3mf", 100)


# ------------------------------------------------------------------ timing, based on the field test
def test_compute_delay_matches_field_test():
    """31-10-2026: file generated 20:11:25, Send pressed ~20:13:50, printer 'running' 20:14:08,
    delay 40444 s, warm-up began 07:28:13 (= running + delay + 1 s)."""
    from printlater.core import Plan
    plan = Plan(Path("x"), Path("x_start0730.gcode.3mf"), datetime(2026, 11, 1, 7, 30), "warmup", 40444,
                datetime(2026, 10, 31, 20, 11, 25))
    assert abs((plan.warmup_at(datetime(2026, 10, 31, 20, 14, 8)) - datetime(2026, 11, 1, 7, 28, 13)).total_seconds()) <= 1


def test_compute_delay_defaults_and_printing_mode():
    from printlater.config import Settings
    from printlater.delay import DelayError, compute_delay
    t = Settings().timing
    now = datetime(2026, 11, 1, 20, 0, 0)
    target = datetime(2026, 11, 2, 7, 30)
    d = compute_delay(target, now, send_lead_s=t.send_lead_seconds, transfer_s=t.transfer_seconds)
    assert d == 11 * 3600 + 30 * 60 - 80
    dp = compute_delay(target, now, send_lead_s=t.send_lead_seconds, transfer_s=t.transfer_seconds, prep_s=480)
    assert d - dp == 480
    with pytest.raises(DelayError, match="too close"):
        compute_delay(now + timedelta(minutes=1), now, send_lead_s=60, transfer_s=20)
    with pytest.raises(DelayError, match="24 hours"):
        compute_delay(now + timedelta(hours=26), now, send_lead_s=60, transfer_s=20)


def test_make_plan_writes_named_output(tmp_path):
    from printlater import core
    from printlater.config import Settings
    src = sliced_file(tmp_path / "vent.gcode.3mf")
    now = datetime(2026, 11, 1, 20, 0)
    plan = core.make_plan(src, datetime(2026, 11, 2, 7, 30), Settings(), now=now)
    assert plan.output.name == "vent_start0730.gcode.3mf" and plan.output.exists()
    assert plan.job_name == "vent_start0730"
    assert plan.delay_s == 11 * 3600 + 30 * 60 - 80


def test_default_target():
    from printlater.core import default_target
    assert default_target("07:30", datetime(2026, 11, 1, 20, 0)) == datetime(2026, 11, 2, 7, 30)
    assert default_target("22:00", datetime(2026, 11, 1, 20, 0)) == datetime(2026, 11, 1, 22, 0)


def test_read_sliced(tmp_path):
    from printlater import sliced
    s = sliced.read(sliced_file(tmp_path / "a.gcode.3mf"))
    assert s.plates[0].seconds == 2257 and s.plates[0].filaments == ["PETG #FFFFFF"]
    assert s.bed_type == "Textured PEI Plate" and s.printer_model == "N7"


# ------------------------------------------------------------------ Home Assistant
class FakeHA:
    def __init__(self, seq):
        self.seq = list(seq)

    def state(self, ent):
        st, name, changed = self.seq[0]
        if ent.endswith("status"):
            return {"state": st, "last_changed": changed}
        return {"state": name}

    def value(self, ent):
        v = self.state(ent)["state"]
        if ent.endswith("task") and len(self.seq) > 1:
            self.seq.pop(0)
        return v


def test_wait_for_job(monkeypatch):
    from printlater import ha as ham
    from printlater.config import HomeAssistant
    cfg = HomeAssistant(enabled=True, print_status="sensor.x_status", task_name="sensor.x_task")
    h = ham.HA(cfg, token="t")
    fake = FakeHA([("finish", "old", "2026-11-01T19:00:00+00:00"),
                   ("running", "vent_start0730.gcode_plate_1", "2026-11-01T19:14:08+00:00")])
    monkeypatch.setattr(h, "state", fake.state)
    monkeypatch.setattr(h, "value", fake.value)
    t = h.wait_for_job("vent_start0730", timeout_s=5, poll_s=0)
    assert t is not None and t.minute == 14 and t.second == 8


def test_config_example_loads():
    from printlater.config import load
    s = load(ROOT / "config.example.toml")
    assert s.timing.meaning == "warmup" and s.homeassistant.enabled is False


def test_no_ai_references_in_repo():
    bad = ("claude", "anthropic", "chatgpt", "openai", "generated by", " llm", "copilot")
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix in {".py", ".md", ".toml", ".yaml", ".ps1", ".txt"} and "test_printlater" not in p.name:
            text = p.read_text(encoding="utf-8", errors="ignore").lower()
            assert not any(b in text for b in bad), f"{p.name} contains a forbidden reference"


# ------------------------------------------------------------------ packaged exe
def test_menu_command_script_and_frozen(monkeypatch):
    from printlater import winsys
    cmd, icon = winsys.menu_command()
    assert cmd.endswith('"run.py" plan "%1"') or 'run.py" plan "%1"' in cmd
    monkeypatch.setattr(winsys, "FROZEN", True)
    monkeypatch.setattr(sys, "executable", r"C:\Users\x\AppData\Local\Programs\PrintLater\PrintLater.exe")
    cmd, icon = winsys.menu_command()
    assert cmd == r'"C:\Users\x\AppData\Local\Programs\PrintLater\PrintLater.exe" plan "%1"'
    assert icon.endswith("PrintLater.exe")


def test_no_console_writes_log(tmp_path, monkeypatch):
    import run
    monkeypatch.setattr(run, "HAS_CONSOLE", False)
    src = sliced_file(tmp_path / "job.gcode.3mf")
    when = (datetime.now() + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M")
    assert run.main(["make", str(src), "--at", when]) == 0
    from printlater.config import data_dir
    log = (data_dir() / "printlater.log").read_text(encoding="utf-8")
    assert "_start" in log and "delay" in log
    assert run.main(["bogus"]) == 2
    assert "invalid command line" in (data_dir() / "printlater.log").read_text(encoding="utf-8")


# ------------------------------------------------------------------ 1.2: status, strict HA, queue
class RecHA:
    """Records service calls and answers state requests from a dict."""
    def __init__(self, states=None, items=None):
        self.states, self.items, self.calls = states or {}, items or [], []

    def __call__(self, method, path, body=None):
        if method == "GET" and path.startswith("/api/states/"):
            ent = path.rsplit("/", 1)[1]
            if ent not in self.states:
                from printlater.ha import HAError
                raise HAError(f"Home Assistant GET {path}: HTTP 404")
            return {"state": self.states[ent], "last_changed": "2026-11-11T06:00:00+00:00"}
        if "get_items" in path:
            return {"changed_states": [], "service_response": {body["entity_id"]: {"items": self.items}}}
        self.calls.append((path.removeprefix("/api/services/"), body))
        return []


def make(rec, **cfg):
    from printlater import ha as ham
    from printlater.config import HomeAssistant
    h = ham.HA(HomeAssistant(enabled=True, **cfg), token="t")
    h._req = rec
    return h


def test_set_plan_status_name_and_flag():
    rec = RecHA()
    h = make(rec, plan_name="input_text.n", plan_status="input_text.s", planned_flag="input_boolean.f",
             planned_start="input_datetime.d")
    h.set_plan("planned", "x" * 150, datetime(2026, 11, 12, 7, 30))
    services = [c[0] for c in rec.calls]
    assert services == ["input_text/set_value", "input_text/set_value", "input_datetime/set_datetime",
                        "input_boolean/turn_on"]
    assert len(rec.calls[0][1]["value"]) == 100 and rec.calls[1][1]["value"] == "planned"
    rec.calls.clear()
    h.set_plan("failed")
    assert [c[0] for c in rec.calls] == ["input_text/set_value", "input_boolean/turn_off"]
    with pytest.raises(ValueError):
        h.set_plan("bogus")


def test_missing_entity_is_reported_clearly():
    from printlater.ha import HAError
    h = make(RecHA({"sensor.s": "idle"}), print_status="sensor.missing")
    with pytest.raises(HAError, match="sensor.missing does not exist"):
        h.check_entities()
    h = make(RecHA({"sensor.s": "idle"}), print_status="sensor.s", plan_status="input_text.missing")
    assert h.check_entities() == ["input_text.missing"] and h.cfg.plan_status == ""


def test_queue_roundtrip():
    from printlater.ha import QueueItem
    wish = datetime(2026, 11, 12, 7, 30)
    d = QueueItem.describe(r"C:\prints\a.gcode.3mf", wish)
    rec = RecHA(items=[{"uid": "u1", "summary": "a", "description": d},
                       {"uid": "u2", "summary": "b", "description": QueueItem.describe("b.gcode.3mf", None)}])
    h = make(rec, queue_todo="todo.q")
    items = h.queue_items()
    assert items[0].file == r"C:\prints\a.gcode.3mf" and items[0].wish == wish and items[1].wish is None
    h.queue_add("c", "c.gcode.3mf", None)
    h.queue_done("u1")
    assert rec.calls[0][0] == "todo/add_item" and "due_datetime" not in rec.calls[0][1]
    assert rec.calls[1] == ("todo/update_item", {"entity_id": "todo.q", "item": "u1", "status": "completed"})


def test_printer_that_stays_offline_raises(monkeypatch):
    from printlater import ha as ham
    rec = RecHA({"switch.p": "off", "binary_sensor.on": "off"})
    h = make(rec, plug="switch.p", online="binary_sensor.on", boot_wait_seconds=0)
    monkeypatch.setattr(ham.time, "sleep", lambda s: None)
    with pytest.raises(ham.HAError, match="did not come online"):
        h.ensure_printer_on()


def test_texts_complete_in_both_languages():
    from printlater.text import T
    assert T["en"].keys() == T["nl"].keys()


def _gui(monkeypatch):
    """Import the dialog module; tkinter is stubbed where it is not installed (CI on Linux)."""
    import types
    try:
        import tkinter.ttk  # noqa: F401
    except ImportError:
        tk = types.ModuleType("tkinter")
        tk.ttk, tk.messagebox = types.ModuleType("tkinter.ttk"), types.ModuleType("tkinter.messagebox")
        for name, mod in (("tkinter", tk), ("tkinter.ttk", tk.ttk), ("tkinter.messagebox", tk.messagebox)):
            monkeypatch.setitem(sys.modules, name, mod)
        monkeypatch.delitem(sys.modules, "printlater.gui", raising=False)
    from printlater import gui
    return gui


def test_connect_is_strict_unless_configured(monkeypatch):
    gui = _gui(monkeypatch)
    from printlater.config import Settings
    from printlater.text import tr
    L = lambda k, **kw: tr("nl", k, **kw)  # noqa: E731
    s = Settings()
    s.homeassistant.enabled = True
    s.homeassistant.print_status = "sensor.s"

    def broken():
        raise OSError("connection refused")
    with pytest.raises(RuntimeError, match="Niet ingepland"):
        gui.connect_ha(s, broken, L, lambda m: None)
    warned = []
    s.homeassistant.continue_without_ha = True
    assert gui.connect_ha(s, broken, L, warned.append) is None and "Ik ga verder zonder" in warned[0]
    s.homeassistant.enabled = False
    assert gui.connect_ha(s, broken, L, warned.append) is None


def test_busy_message_names_task_and_plan(monkeypatch):
    gui = _gui(monkeypatch)
    from printlater.text import tr
    rec = RecHA({"sensor.t": "zolder_mount", "input_text.s": "waiting", "input_text.n": "vent_start0730",
                 "input_datetime.d": "2026-11-12 07:30:00"})
    h = make(rec, task_name="sensor.t", plan_status="input_text.s", plan_name="input_text.n",
             planned_start="input_datetime.d")
    msg = gui.busy_message(h, "running", lambda k, **kw: tr("nl", k, **kw), True)
    assert "running, zolder_mount" in msg and "vent_start0730, start 2026-11-12 07:30" in msg
    assert "In wachtrij" in msg
