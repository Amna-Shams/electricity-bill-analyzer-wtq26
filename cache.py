"""Disk cache per (bill, step). Entries are keyed by a hash of the inputs, so editing a prompt or image invalidates them."""
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def digest(*items: Any) -> str:
    h = hashlib.sha256()
    for it in items:
        h.update(it if isinstance(it, bytes) else json.dumps(it, sort_keys=True, default=str).encode())
        h.update(b"\x00")
    return h.hexdigest()


class Cache:
    def __init__(self, directory: Path, enabled: bool = True):
        self.dir = Path(directory)
        self.enabled = enabled
        if enabled:
            self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, bill_id: str, step: str) -> Path:
        return self.dir / f"{bill_id}.{step}.json"

    def get(self, bill_id: str, step: str, key: str) -> Any | None:
        if not self.enabled:
            return None
        p = self._path(bill_id, step)
        try:
            entry = json.loads(p.read_text(encoding="utf-8"))
            if entry.get("key") == key:
                log.info("[%s] %s: cache hit", bill_id, step)
                return entry["value"]
        except (OSError, ValueError):
            pass
        return None

    def put(self, bill_id: str, step: str, key: str, value: Any) -> None:
        if not self.enabled:
            return
        self._path(bill_id, step).write_text(
            json.dumps({"key": key, "value": value}, ensure_ascii=False), encoding="utf-8")
