"""In-memory registry store with TTL-based expiry."""

import threading
import time
from datetime import datetime
from typing import Optional

from .models import RegistrationRequest, RegistryEntry

TTL_SECONDS = 300  # 5 minutes without heartbeat → stale (excluded from listings)
HARD_TTL_SECONDS = 600  # 10 minutes → deleted entirely


class RegistryStore:
    def __init__(self, ttl_seconds: int = TTL_SECONDS):
        self._entries: dict[str, RegistryEntry] = {}
        self._lock = threading.RLock()
        self._ttl = ttl_seconds

        t = threading.Thread(target=self._cleaner, daemon=True, name="registry-cleaner")
        t.start()

    def register(self, req: RegistrationRequest) -> RegistryEntry:
        now = datetime.utcnow().isoformat()
        entry = RegistryEntry(
            name=req.name,
            url=req.url,
            capabilities=req.capabilities,
            tagline=req.tagline,
            registered_at=now,
            last_heartbeat=now,
        )
        with self._lock:
            self._entries[entry.id] = entry
        return entry

    def deregister(self, entry_id: str, token: str) -> bool:
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None or entry.token != token:
                return False
            del self._entries[entry_id]
            return True

    def heartbeat(self, entry_id: str, token: str, availability: Optional[str] = None) -> Optional[RegistryEntry]:
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None or entry.token != token:
                return None
            entry.last_heartbeat = datetime.utcnow().isoformat()
            if availability:
                entry.availability = availability
            return entry

    def list_all(self, capability: Optional[str] = None) -> list[RegistryEntry]:
        with self._lock:
            now = time.time()
            result = []
            for entry in self._entries.values():
                last = datetime.fromisoformat(entry.last_heartbeat).timestamp()
                if now - last > self._ttl:
                    continue  # stale — heartbeat overdue
                if capability and capability not in entry.capabilities:
                    continue
                result.append(entry)
            return sorted(result, key=lambda e: e.registered_at)

    def get(self, entry_id: str) -> Optional[RegistryEntry]:
        with self._lock:
            return self._entries.get(entry_id)

    def count(self) -> int:
        return len(self.list_all())

    def _cleaner(self):
        """Periodically hard-delete entries that have been silent for 2× TTL."""
        while True:
            time.sleep(60)
            now = time.time()
            with self._lock:
                stale = [
                    eid for eid, entry in self._entries.items()
                    if now - datetime.fromisoformat(entry.last_heartbeat).timestamp() > self._ttl * 2
                ]
                for eid in stale:
                    del self._entries[eid]
