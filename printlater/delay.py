"""Low-power delayed start for sliced Bambu Lab files (.gcode.3mf).

A block is inserted at the very top of each plate's G-code, before the printer's own
start sequence. It switches heaters, controllable fans and LEDs off, releases the
stepper motors and then waits in short dwell steps. When the wait is over the motors
are re-enabled and the normal start G-code runs (homing, heating, levelling, ...).

The plate's .md5 file inside the archive is updated so the printer accepts the file.
"""
from __future__ import annotations

import hashlib
import re
import zipfile
from datetime import datetime
from pathlib import Path

MARKER = "; EXECUTABLE_BLOCK_START\n"
TAG = "PRINTLATER DELAYED START"
CHUNK_S = 90                 # Bambu firmware caps a single dwell at about 90 s
MAX_DELAY_S = 24 * 3600


class DelayError(Exception):
    pass


def delay_block(delay_s: int, note: str = "") -> str:
    if not 0 < delay_s <= MAX_DELAY_S:
        raise DelayError(f"Delay of {delay_s} s is outside 1 s .. 24 h.")
    lines = [
        f"; ===== {TAG}: {delay_s} s {note}=====",
        "M140 S0 ; bed heater off",
        "M104 S0 ; hotend heater off",
        "M106 S0 ; part cooling fan off",
        "M106 P1 S0",
        "M106 P2 S0 ; aux fan off",
        "M106 P3 S0 ; chamber fan off",
        "M106 P10 S0 ; second aux fan off (where fitted)",
        "M960 S5 P0 ; toolhead logo LED off",
        "M960 S0 P0 ; calibration LEDs / lasers off",
        "M960 S1 P0",
        "M960 S2 P0",
        "M960 S4 P0",
        "M18 ; release stepper motors while waiting",
    ]
    lines += [f"M400 S{min(CHUNK_S, delay_s - i)}" for i in range(0, delay_s, CHUNK_S)]
    lines += ["M17 ; re-enable stepper motors, normal start sequence follows", f"; ===== END {TAG} ====="]
    return "\n".join(lines) + "\n"


def plates_in(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        return sorted(n for n in z.namelist() if re.fullmatch(r"Metadata/plate_\d+\.gcode", n))


def has_delay(path: Path) -> bool:
    with zipfile.ZipFile(path) as z:
        return any(TAG in z.read(p).decode("utf-8", "replace")[:20000] for p in plates_in(path))


def apply_delay(src: Path, dst: Path, delay_s: int, note: str = "") -> dict:
    """Write a copy of `src` to `dst` with the delayed-start block in every plate."""
    plates = plates_in(src)
    if not plates:
        raise DelayError("No sliced G-code in this file. Export it with 'Export plate sliced file'.")
    new: dict[str, bytes] = {}
    with zipfile.ZipFile(src) as zin:
        for p in plates:
            g = zin.read(p).decode("utf-8")
            if TAG in g:
                raise DelayError("This file already contains a delayed start. Use the original export.")
            if g.count(MARKER) != 1:
                raise DelayError(f"{p}: start marker not found exactly once; file layout not recognised.")
            data = g.replace(MARKER, MARKER + delay_block(delay_s, note), 1).encode("utf-8")
            new[p] = data
            new[p + ".md5"] = hashlib.md5(data).hexdigest().upper().encode()
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                zout.writestr(info, new.get(info.filename, zin.read(info.filename)),
                              compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(dst) as z:            # verify what was written
        if z.testzip() is not None:
            raise DelayError("Archive check failed.")
        names = z.namelist()
        for p in plates:
            if p + ".md5" in names and z.read(p + ".md5").decode().strip() != hashlib.md5(z.read(p)).hexdigest().upper():
                raise DelayError(f"Checksum mismatch for {p}.")
    return {"plates": plates, "delay_s": delay_s, "steps": -(-delay_s // CHUNK_S)}


def compute_delay(target: datetime, generated_at: datetime, *, send_lead_s: int, transfer_s: int,
                  prep_s: int = 0) -> int:
    """Seconds to wait so the printer starts at `target`.

    send_lead_s  expected time between generating the file and pressing Send
    transfer_s   time between pressing Send and the printer starting to run the G-code
    prep_s       subtract the printer's own preparation time when `target` means
                 "first layer starts" instead of "printer starts warming up"
    """
    d = int((target - generated_at).total_seconds()) - send_lead_s - transfer_s - prep_s
    if d < 60:
        raise DelayError("The start time is too close. Choose a time at least a few minutes ahead.")
    if d > MAX_DELAY_S:
        raise DelayError("The start time is more than 24 hours ahead.")
    return d
