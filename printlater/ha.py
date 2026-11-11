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
from dataclasses import dataclass
from datetime import datetime

from .config import HomeAssistant, data_dir
from . import winsys

TOKEN_FILE = "ha_token.bin"
BUSY = {"running", "prepare", "pause", "slicing"}
STATUSES = ("none", "planned", "waiting", "started", "failed")
TEXT_MAX = 100                 # default max length of an input_text


@dataclass
class QueueItem:
    uid: str
    name: str
    file: str
    wish: datetime | None      # None = as soon as possible

    @staticmethod
    def describe(file: str, wish: datetime | None) -> str:
        return f"file={file}\nwish={wish:%Y-%m-%d %H:%M}" if wish else f"file={file}\nwish=asap"

    @classmethod
    def parse(cls, item: dict) -> "QueueItem":
        fields = dict(line.split("=", 1) for line in (item.get("description") or "").splitlines() if "=" in line)
        wish = None
        if fields.get("wish", "asap") != "asap":
            try:
                wish = datetime.strptime(fields["wish"].strip(), "%Y-%m-%d %H:%M")
            except ValueError:
                wish = None
        return cls(item.get("uid", ""), item.get("summary", ""), fields.get("file", "").strip(), wish)


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
        try:
            return self._req("GET", f"/api/states/{entity_id}")
        except HAError as e:
            if "HTTP 404" in str(e):
                raise HAError(f"Entity {entity_id} does not exist in Home Assistant.") from e
            raise

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
                while self.value(c.online) != "on":
                    if time.monotonic() > deadline:
                        raise HAError(f"The printer did not come online within {c.boot_wait_seconds} s.")
                    time.sleep(5)
            time.sleep(10)

    def printer_busy(self) -> str | None:
        if not self.cfg.print_status:
            return None
        s = self.value(self.cfg.print_status).lower()
        return s if s in BUSY else None

    def check_entities(self) -> list[str]:
        """Fail early when a configured entity does not exist (typo, renamed after a migration).
        The optional status and queue entities are switched off instead; returns their names."""
        c = self.cfg
        for ent in (c.plug, c.online, c.print_status, c.task_name, c.planned_flag, c.planned_start):
            if ent:
                self.state(ent)
        dropped = []
        for attr in ("plan_name", "plan_status", "queue_todo"):
            ent = getattr(c, attr)
            if ent:
                try:
                    self.state(ent)
                except HAError as e:
                    if "does not exist" not in str(e):
                        raise
                    dropped.append(ent)
                    setattr(c, attr, "")
        return dropped

    def record_plan(self, start: datetime | None) -> None:
        c = self.cfg
        if c.planned_start and start:
            self.call("input_datetime.set_datetime",
                      {"entity_id": c.planned_start, "datetime": start.strftime("%Y-%m-%d %H:%M:%S")})
        if c.planned_flag:
            self.call(f"input_boolean.turn_{'on' if start else 'off'}", {"entity_id": c.planned_flag})

    def set_plan(self, status: str, name: str | None = None, start: datetime | None = None) -> None:
        """Publish the plan: status (see STATUSES), job name and expected start."""
        if status not in STATUSES:
            raise ValueError(status)
        c = self.cfg
        if c.plan_name and name is not None:
            self.call("input_text.set_value", {"entity_id": c.plan_name, "value": name[:TEXT_MAX] or "-"})
        if c.plan_status:
            self.call("input_text.set_value", {"entity_id": c.plan_status, "value": status})
        if status in ("planned", "waiting"):
            self.record_plan(start)
        elif c.planned_flag:
            self.call("input_boolean.turn_off", {"entity_id": c.planned_flag})

    def current_plan(self) -> tuple[str, str, str]:
        """(status, name, start) as stored in Home Assistant; empty strings when not configured."""
        c = self.cfg
        get = lambda e: self.value(e) if e else ""  # noqa: E731
        return get(c.plan_status), get(c.plan_name), get(c.planned_start)

    def task(self) -> str:
        return self.value(self.cfg.task_name) if self.cfg.task_name else ""

    # ---------------------------------------------------------------- queue (todo list)
    def queue_items(self) -> list[QueueItem]:
        c = self.cfg
        if not c.queue_todo:
            return []
        r = self._req("POST", "/api/services/todo/get_items?return_response",
                      {"entity_id": c.queue_todo, "status": "needs_action"})
        items = ((r or {}).get("service_response") or {}).get(c.queue_todo, {}).get("items", [])
        return [QueueItem.parse(i) for i in items]

    def queue_add(self, name: str, file: str, wish: datetime | None) -> None:
        c = self.cfg
        if not c.queue_todo:
            raise HAError("No queue configured (homeassistant.queue_todo).")
        data = {"entity_id": c.queue_todo, "item": name, "description": QueueItem.describe(file, wish)}
        if wish:
            data["due_datetime"] = wish.strftime("%Y-%m-%d %H:%M:%S")
        self.call("todo.add_item", data)

    def queue_done(self, uid: str) -> None:
        if self.cfg.queue_todo and uid:
            self.call("todo.update_item", {"entity_id": self.cfg.queue_todo, "item": uid, "status": "completed"})

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
