"""Registro de ejecución (JSONL) con marcas de tiempo ET/CDMX/UTC."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .timing import ET, MX


class RunLog:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, event: str, **detail) -> dict:
        now = dt.datetime.now(dt.timezone.utc)
        rec = {"utc": now.isoformat(timespec="seconds"),
               "et": now.astimezone(ET).strftime("%Y-%m-%d %H:%M:%S %Z"),
               "cdmx": now.astimezone(MX).strftime("%H:%M:%S"),
               "event": event, **detail}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()]

    def first(self, event: str) -> dict | None:
        return next((r for r in self.read() if r["event"] == event), None)

    def last(self, event: str) -> dict | None:
        recs = [r for r in self.read() if r["event"] == event]
        return recs[-1] if recs else None
