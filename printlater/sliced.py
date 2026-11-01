"""Read basic facts from a sliced Bambu Lab .gcode.3mf (plates, time, weight, material)."""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET


class SlicedFileError(Exception):
    pass


@dataclass
class Plate:
    index: int
    seconds: int | None = None
    grams: float | None = None
    filaments: list[str] = field(default_factory=list)


@dataclass
class SlicedFile:
    path: Path
    plates: list[Plate]
    printer_model: str | None
    bed_type: str | None

    @property
    def name(self) -> str:
        return self.path.name.removesuffix(".3mf").removesuffix(".gcode")


def read(path: Path) -> SlicedFile:
    if not zipfile.is_zipfile(path):
        raise SlicedFileError(f"{path.name} is not a 3MF file.")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        idx = sorted(int(m.group(1)) for n in names if (m := re.fullmatch(r"Metadata/plate_(\d+)\.gcode", n)))
        if not idx:
            raise SlicedFileError(
                f"{path.name} contains no sliced G-code. In Bambu Studio use "
                "'Export plate sliced file' and select the .gcode.3mf it creates.")
        plates = {i: Plate(i) for i in idx}
        model = bed = None
        if "Metadata/slice_info.config" in names:
            try:
                root = ET.fromstring(z.read("Metadata/slice_info.config"))
                for p in root.iter("plate"):
                    meta = {m.get("key"): m.get("value") for m in p.findall("metadata")}
                    i = int(meta.get("index") or 0)
                    if i not in plates:
                        continue
                    if meta.get("prediction"):
                        plates[i].seconds = int(float(meta["prediction"]))
                    if meta.get("weight"):
                        plates[i].grams = float(meta["weight"])
                    model = model or meta.get("printer_model_id")
                    plates[i].filaments = [f"{f.get('type', '?')} {f.get('color', '')}".strip()
                                           for f in p.findall("filament")]
            except (ET.ParseError, ValueError):
                pass
        head = z.read(f"Metadata/plate_{idx[0]}.gcode")[:400000].decode("utf-8", "replace")
        m = re.search(r"; curr_bed_type = (.+)", head)
        bed = m.group(1).strip() if m else None
    return SlicedFile(path, [plates[i] for i in idx], model, bed)
