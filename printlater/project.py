"""Plan straight from a saved Bambu Studio project: list its plates and slice one with the
Bambu Studio command line (``--slice N --export-3mf``), so no manual export is needed."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

# printer_model_id that Bambu Studio writes into slice_info.config when it exports from the GUI.
# The command line leaves it empty. Only models seen in a real GUI export are listed here.
PRINTER_MODEL_IDS = {
    "Bambu Lab P2S": "N7",
}


class ProjectError(Exception):
    pass


@dataclass
class ProjectPlate:
    index: int
    name: str

    def label(self) -> str:
        return f"{self.index}: {self.name}" if self.name else str(self.index)


def is_sliced(path: Path) -> bool:
    """True for a .gcode.3mf that already holds sliced G-code."""
    try:
        with zipfile.ZipFile(path) as z:
            return any(re.fullmatch(r"Metadata/plate_\d+\.gcode", n) for n in z.namelist())
    except zipfile.BadZipFile:
        return False


def read_plates(path: Path) -> list[ProjectPlate]:
    """Plates of a project, with the names given in Bambu Studio."""
    with zipfile.ZipFile(path) as z:
        try:
            ms = z.read("Metadata/model_settings.config").decode("utf-8", "replace")
        except KeyError:
            return [ProjectPlate(1, "")]
    plates = []
    for block in re.findall(r"<plate>(.*?)</plate>", ms, re.S):
        meta = dict(re.findall(r'<metadata key="([^"]+)" value="([^"]*)"', block))
        try:
            plates.append(ProjectPlate(int(meta.get("plater_id", "0")), meta.get("plater_name", "")))
        except ValueError:
            continue
    plates = [p for p in plates if p.index > 0]
    return sorted(plates, key=lambda p: p.index) or [ProjectPlate(1, "")]


def printer_model(path: Path) -> str:
    """Printer the project is set up for, e.g. 'Bambu Lab P2S'."""
    try:
        with zipfile.ZipFile(path) as z:
            cfg = json.loads(z.read("Metadata/project_settings.config"))
        return str(cfg.get("printer_model") or "")
    except (KeyError, ValueError, zipfile.BadZipFile):
        return ""


def check_printer(path: Path, expected: str) -> None:
    """Refuse a project made for another printer: the command line slices exactly what is saved,
    while Bambu Studio's window converts a downloaded project to your printer when you open it."""
    have = printer_model(path)
    if expected and have and have != expected:
        raise ProjectError(
            f"{path.name} is set up for a {have}, not your {expected}. Open it in Bambu Studio, "
            f"select your printer, save the project and plan again.")


def output_name(src: Path, plate: ProjectPlate, plate_count: int) -> str:
    stem = src.name.removesuffix(".3mf")
    if plate_count > 1:
        stem += f"_{_safe(plate.name) or 'plate' + str(plate.index)}"
    return stem + ".gcode.3mf"


def _safe(s: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "", s).strip().replace(" ", "_")


def slice_command(studio: str, src: Path, plate: int, outdir: Path, name: str) -> list[str]:
    return [studio, "--slice", str(plate), "--outputdir", str(outdir), "--export-3mf", name, str(src)]


def slice_project(src: Path, plate: ProjectPlate, plate_count: int, studio: str, dest_dir: Path,
                  timeout_s: int = 900) -> Path:
    """Slice one plate with the Bambu Studio command line. Returns the .gcode.3mf in dest_dir."""
    if not studio:
        raise ProjectError("Bambu Studio was not found; set bambu_studio in config.toml.")
    name = output_name(src, plate, plate_count)
    with tempfile.TemporaryDirectory(prefix="printlater_") as tmp:
        cmd = slice_command(studio, src, plate.index, Path(tmp), name)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired as e:
            raise ProjectError(f"Slicing took longer than {timeout_s // 60} minutes and was stopped.") from e
        out = Path(tmp) / name
        if res.returncode != 0 or not out.exists() or not is_sliced(out):
            tail = "\n".join((res.stdout + res.stderr).strip().splitlines()[-5:])
            raise ProjectError(f"Bambu Studio could not slice plate {plate.index} "
                               f"(exit code {res.returncode}).\n{tail}".strip())
        fix_printer_model(out, printer_model(src))
        dest = dest_dir / name
        shutil.move(str(out), dest)
    return dest


def fix_printer_model(path: Path, model: str) -> bool:
    """Fill the empty printer_model_id that the command line leaves in slice_info.config, so the
    file looks like a GUI export to Bambu Studio and the printer. Returns True when changed."""
    pid = PRINTER_MODEL_IDS.get(model)
    if not pid:
        return False
    with zipfile.ZipFile(path) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    changed = False
    out = []
    for info, data in items:
        if info.filename == "Metadata/slice_info.config":
            new = data.replace(b'<metadata key="printer_model_id" value=""/>',
                               f'<metadata key="printer_model_id" value="{pid}"/>'.encode())
            changed = new != data
            data = new
        out.append((info, data))
    if changed:
        tmp = path.with_suffix(".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for info, data in out:
                z.writestr(info, data)
        tmp.replace(path)
    return changed
