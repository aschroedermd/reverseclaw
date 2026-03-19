import json
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any


EVIDENCE_DIR = "human-evidence"
DEFAULT_LOCAL_RETENTION_HOURS = 24 * 30


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


class HumanEvidenceStore:
    def __init__(self, evidence_dir: str = EVIDENCE_DIR, retention_hours: int = DEFAULT_LOCAL_RETENTION_HOURS):
        self._dir = evidence_dir
        self._retention = max(24, int(retention_hours))
        self._lock = threading.RLock()
        os.makedirs(self._dir, exist_ok=True)

    def save_completed_task_bundle(self, task, result: str, signed_receipt: dict[str, Any]):
        bundle = {
            "version": 1,
            "stored_at": _utc_now_iso(),
            "task": {
                "id": task.id,
                "caller_id": task.caller_id,
                "title": task.title,
                "description": task.description,
                "context": task.context,
                "goal_id": getattr(task, "goal_id", None),
                "goal_label": getattr(task, "goal_label", None),
                "capability_required": task.capability_required,
                "deadline_minutes": getattr(task, "deadline_minutes", None),
                "priority": getattr(task, "priority", None),
                "proof_required": bool(getattr(task, "proof_required", False)),
                "success_criteria": getattr(task, "success_criteria", None),
                "created_at": task.created_at,
                "completed_at": getattr(task, "completed_at", None),
            },
            "result": result,
            "signed_receipt": signed_receipt,
        }
        with self._lock:
            self._prune_locked()
            with open(self._path(task.id), "w", encoding="utf-8") as f:
                json.dump(bundle, f, indent=2, ensure_ascii=True)
        return self._path(task.id)

    def prune_expired(self) -> int:
        with self._lock:
            return self._prune_locked()

    def _prune_locked(self) -> int:
        removed = 0
        cutoff = _utc_now() - timedelta(hours=self._retention)
        for fname in os.listdir(self._dir):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(self._dir, fname)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
                if mtime < cutoff:
                    os.remove(path)
                    removed += 1
            except OSError:
                continue
        return removed

    def _path(self, task_id: str) -> str:
        safe_id = os.path.basename(task_id).replace("..", "").replace("/", "")
        return os.path.join(self._dir, f"{safe_id}.json")
