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
    meaning: str                # "warmup", "printing" or "finish"
    delay_s: int
    generated_at: datetime
    lead_s: int = 0             # target minus the moment the printer starts warming up
    transfer_s: int = 20        # expected Send -> running time used for this file

    @property
    def job_name(self) -> str:
        return self.output.name.removesuffix(".3mf").removesuffix(".gcode")

    @property
    def warmup_planned(self) -> datetime:
        """When the printer is planned to start heating and homing."""
        return self.target - timedelta(seconds=self.lead_s)

    def prep_s(self, settings: Settings) -> int:  # kept for older callers
        return self.lead_s

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
    lead = lead_seconds(meaning, info, settings)
    transfer = transfer_seconds(src.stat().st_size, settings)
    d = delay.compute_delay(target, now, send_lead_s=t.send_lead_seconds,
                            transfer_s=transfer, prep_s=lead)
    warmup = target - timedelta(seconds=lead)
    out = output_path(src, warmup if meaning == "finish" else target, settings)
    out.parent.mkdir(parents=True, exist_ok=True)
    note = f"finish {target:%H:%M} " if meaning == "finish" else f"start {target:%H:%M} "
    delay.apply_delay(src, out, d, note=note)
    return Plan(src, out, target, meaning, d, now, lead_s=lead, transfer_s=transfer)


def print_seconds(info) -> int | None:
    """Bambu's estimated total time for the sliced file (all plates), or None if unknown."""
    secs = [p.seconds for p in info.plates]
    return sum(secs) if secs and all(secs) else None


def lead_seconds(meaning: str, info, settings: Settings) -> int:
    """Seconds between the moment the printer starts warming up and the chosen time."""
    t = settings.timing
    if meaning == "printing":
        return int(t.prep_minutes * 60)
    if meaning == "finish":
        total = print_seconds(info)
        if not total:
            raise delay.DelayError("This file has no print time estimate, so 'finished at' cannot be "
                                   "used. Choose when the printer starts instead.")
        # Bambu's estimate already includes its own preparation estimate
        return int(total + t.finish_margin_minutes * 60)
    return 0


def transfer_seconds(size_bytes: int, settings: Settings) -> int:
    """Expected time from pressing Send until the printer runs the file. Large files take longer:
    Bambu Studio uploads them and the printer downloads and unpacks them first."""
    t = settings.timing
    extra_mb = max(0.0, size_bytes / 1_000_000 - 10)
    return int(round(t.transfer_seconds + extra_mb * t.transfer_seconds_per_mb))


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
