"""Planning logic shared by the dialog and the command line."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from . import delay, sliced
from .config import Settings


@dataclass
class Plan:
    source: Path
    output: Path
    target: datetime            # what the user asked for
    meaning: str                # "warmup" or "printing"
    delay_s: int
    generated_at: datetime

    @property
    def job_name(self) -> str:
        return self.output.name.removesuffix(".3mf").removesuffix(".gcode")

    def prep_s(self, settings: Settings) -> int:
        return int(settings.timing.prep_minutes * 60) if self.meaning == "printing" else 0

    def warmup_at(self, running_since: datetime) -> datetime:
        """The dwell starts within about a second of the printer reporting 'running'."""
        return running_since + timedelta(seconds=self.delay_s)


def output_path(src: Path, target: datetime, settings: Settings) -> Path:
    folder = Path(settings.output_dir) if settings.output_dir else src.parent
    stem = src.name.removesuffix(".3mf").removesuffix(".gcode")
    return folder / f"{stem}_start{target:%H%M}.gcode.3mf"


def make_plan(src: Path, target: datetime, settings: Settings, *, meaning: str | None = None,
              now: datetime | None = None) -> Plan:
    info = sliced.read(src)                       # validates: sliced Bambu file
    if delay.has_delay(src):
        raise delay.DelayError("This file already contains a delayed start. Use the original export.")
    now = now or datetime.now()
    meaning = meaning or settings.timing.meaning
    t = settings.timing
    prep = int(t.prep_minutes * 60) if meaning == "printing" else 0
    d = delay.compute_delay(target, now, send_lead_s=t.send_lead_seconds,
                            transfer_s=t.transfer_seconds, prep_s=prep)
    out = output_path(src, target, settings)
    out.parent.mkdir(parents=True, exist_ok=True)
    delay.apply_delay(src, out, d, note=f"start {target:%H:%M} ")
    del info
    return Plan(src, out, target, meaning, d, now)


def parse_when(date_s: str, time_s: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    try:
        dt = datetime.strptime(f"{date_s.strip()} {time_s.strip()}", "%Y-%m-%d %H:%M")
    except ValueError as e:
        raise delay.DelayError("Use date YYYY-MM-DD and time HH:MM.") from e
    return dt


def default_target(default_time: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    h, m = (int(x) for x in default_time.split(":"))
    dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return dt if dt > now + timedelta(minutes=10) else dt + timedelta(days=1)
