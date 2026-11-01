"""Optional Home Assistant link: power the printer, check it is free, record the plan,
and confirm when the printer has accepted the job."""
from __future__ import annotations

import http.client
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime

from .config import HomeAssistant, data_dir
from . import winsys

TOKEN_FILE = "ha_token.bin"
BUSY = {"running", "prepare", "pause", "slicing"}


class HAError(Exception):
    pass


def save_token(token: str) -> None:
    (data_dir() / TOKEN_FILE).write_bytes(winsys.protect(token.strip().encode()))


def load_token() -> str:
    if os.environ.get("PRINTLATER_HA_TOKEN"):
        return os.environ["PRINTLATER_HA_TOKEN"]
    f = data_dir() / TOKEN_FILE
    if not f.exists():
        raise HAError("No Home Assistant token stored. Run: run.py set-token")
    return winsys.unprotect(f.read_bytes()).decode()


class HA:
    def __init__(self, cfg: HomeAssistant, token: str | None = None):
        self.cfg = cfg
        self.token = token if token is not None else load_token()
        self.ctx = None if cfg.verify_ssl else ssl._create_unverified_context()  # noqa: S323 - opt-in

    def _req(self, method: str, path: str, body: dict | None = None):
        url = self.cfg.url.rstrip("/") + path
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {self.token}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15, context=self.ctx) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raise HAError(f"Home Assistant {method} {path}: HTTP {e.code}") from e
        except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as e:
            raise HAError(f"Home Assistant not reachable ({url}): {e}") from e

    def state(self, entity_id: str) -> dict:
        return self._req("GET", f"/api/states/{entity_id}")

    def value(self, entity_id: str) -> str:
        return self.state(entity_id)["state"]

    def call(self, service: str, data: dict) -> None:
        domain, name = service.split(".", 1)
        self._req("POST", f"/api/services/{domain}/{name}", data)

    # ---------------------------------------------------------------- high level
    def ensure_printer_on(self, progress=lambda m: None) -> None:
        c = self.cfg
        if not c.plug:
            return
        if self.value(c.plug) != "on":
            progress("Switching the printer on...")
            self.call(f"{c.plug.split('.', 1)[0]}.turn_on", {"entity_id": c.plug})
            if c.online:
                deadline = time.monotonic() + c.boot_wait_seconds
                time.sleep(15)
                while time.monotonic() < deadline:
                    if self.value(c.online) == "on":
                        break
                    time.sleep(5)
            time.sleep(10)

    def printer_busy(self) -> str | None:
        if not self.cfg.print_status:
            return None
        s = self.value(self.cfg.print_status).lower()
        return s if s in BUSY else None

    def record_plan(self, start: datetime | None) -> None:
        c = self.cfg
        if c.planned_start and start:
            self.call("input_datetime.set_datetime",
                      {"entity_id": c.planned_start, "datetime": start.strftime("%Y-%m-%d %H:%M:%S")})
        if c.planned_flag:
            self.call(f"input_boolean.turn_{'on' if start else 'off'}", {"entity_id": c.planned_flag})

    def wait_for_job(self, job_name: str, timeout_s: int = 900, poll_s: int = 3) -> datetime | None:
        """Wait until the printer runs a job whose name contains `job_name`.
        Returns the local time it switched to 'running', or None on timeout."""
        c = self.cfg
        if not (c.print_status and c.task_name):
            return None
        deadline = time.monotonic() + timeout_s
        key = job_name.lower()[:40]
        while time.monotonic() < deadline:
            try:
                st = self.state(c.print_status)
                task = self.value(c.task_name).lower()
                if st["state"] == "running" and key in task:
                    changed = datetime.fromisoformat(st["last_changed"]).astimezone().replace(tzinfo=None)
                    return changed
            except HAError:
                pass
            time.sleep(poll_s)
        return None
