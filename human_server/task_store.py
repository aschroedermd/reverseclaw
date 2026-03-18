"""File-backed task persistence for the Human API Server."""

import json
import os
import threading
from typing import Optional

from .models import TaskRecord, TaskStatus

TASKS_DIR = "human-tasks"


class TaskStore:
    def __init__(self, tasks_dir: str = TASKS_DIR):
        self._dir = tasks_dir
        self._lock = threading.RLock()
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, task_id: str) -> str:
        # Sanitize to prevent directory traversal
        safe_id = os.path.basename(task_id).replace("..", "").replace("/", "")
        return os.path.join(self._dir, f"{safe_id}.json")

    def save(self, task: TaskRecord) -> TaskRecord:
        with self._lock:
            path = self._path(task.id)
            with open(path, "w") as f:
                f.write(task.model_dump_json(indent=2))
        return task

    def get(self, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            path = self._path(task_id)
            if not os.path.exists(path):
                return None
            with open(path) as f:
                return TaskRecord.model_validate(json.load(f))

    def list_all(self, status_filter: Optional[str] = None) -> list[TaskRecord]:
        with self._lock:
            tasks = []
            if not os.path.exists(self._dir):
                return tasks
            for fname in sorted(os.listdir(self._dir)):
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(self._dir, fname)
                try:
                    with open(path) as f:
                        task = TaskRecord.model_validate(json.load(f))
                    if status_filter is None or task.status == status_filter:
                        tasks.append(task)
                except (json.JSONDecodeError, Exception):
                    continue
            return tasks

    def update_status(self, task_id: str, status: str, **kwargs) -> Optional[TaskRecord]:
        with self._lock:
            task = self.get(task_id)
            if task is None:
                return None
            task.status = status
            for k, v in kwargs.items():
                if hasattr(task, k):
                    setattr(task, k, v)
            return self.save(task)

    def delete(self, task_id: str) -> bool:
        with self._lock:
            path = self._path(task_id)
            if os.path.exists(path):
                os.remove(path)
                return True
            return False

    def count_by_status(self) -> dict[str, int]:
        with self._lock:
            counts = {s.value: 0 for s in TaskStatus}
            for task in self.list_all():
                if task.status in counts:
                    counts[task.status] += 1
            return counts
