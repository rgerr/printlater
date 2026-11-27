"""Settings: loaded from %LOCALAPPDATA%\\PrintLater\\config.toml with safe defaults."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

APP = "PrintLater"
MEANINGS = ("warmup", "printing", "finish")


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    p = Path(base) / APP
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    return data_dir() / "config.toml"


@dataclass
class Timing:
    default_time: str = "07:30"
    # What the chosen time means: "warmup" = printer starts heating/homing,
    # "printing" = first layer starts (preparation time is subtracted),
    # "finish" = print is done (Bambu's estimated total time and a margin are subtracted).
    meaning: str = "warmup"
    prep_minutes: float = 8.0      # measured on a P2S with AMS load + auto levelling: ~8 min
    finish_margin_minutes: float = 10.0  # "finish": aim this much earlier; estimates can run over
    send_lead_seconds: int = 60    # time from closing the dialog to pressing Send in Bambu Studio
    transfer_seconds: int = 20     # Send -> printer runs the file, for files up to 10 MB (15-25 s)
    transfer_seconds_per_mb: float = 1.6  # extra per MB above 10 MB (74 MB took ~125 s on a P2S)


@dataclass
class HomeAssistant:
    enabled: bool = False
    url: str = "http://homeassistant.local:8123"
    verify_ssl: bool = True
    plug: str = ""                 # switch.* that powers the printer (optional)
    online: str = ""               # binary_sensor.*_online from the Bambu Lab integration (optional)
    print_status: str = ""         # sensor.*_print_status
    task_name: str = ""            # sensor.*_task_name
    planned_flag: str = ""         # input_boolean.* set on when a delayed start is planned (optional)
    planned_start: str = ""        # input_datetime.* receives the expected start time (optional)
    plan_name: str = ""            # input_text.* receives the name of the planned job (optional)
    plan_status: str = ""          # input_text.* receives none/planned/waiting/started/failed (optional)
    queue_todo: str = ""           # todo.* list used as print queue (optional)
    continue_without_ha: bool = False  # True: plan anyway when Home Assistant cannot be reached
    boot_wait_seconds: int = 120


@dataclass
class Settings:
    timing: Timing = field(default_factory=Timing)
    homeassistant: HomeAssistant = field(default_factory=HomeAssistant)
    bambu_studio: str = ""         # path to bambu-studio.exe; empty = auto-detect
    output_dir: str = ""           # where delayed files are written; empty = next to the source file
    language: str = ""             # "en" or "nl"; empty = follow Windows


def _fill(obj, data: dict, section: str):
    known = {f.name for f in fields(obj)}
    for k, v in data.items():
        if k not in known:
            raise ValueError(f"Unknown setting [{section}] {k}")
        setattr(obj, k, v)


def load(path: Path | None = None) -> Settings:
    s = Settings()
    path = path or config_path()
    if not path.exists():
        return s
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    _fill(s.timing, raw.pop("timing", {}), "timing")
    _fill(s.homeassistant, raw.pop("homeassistant", {}), "homeassistant")
    for k, v in raw.items():
        if k not in ("bambu_studio", "output_dir", "language"):
            raise ValueError(f"Unknown setting {k}")
        setattr(s, k, v)
    if s.timing.meaning not in MEANINGS:
        raise ValueError("timing.meaning must be 'warmup', 'printing' or 'finish'")
    return s
