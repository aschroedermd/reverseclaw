"""Notification system for incoming tasks."""

import threading
from typing import Optional

from .models import TaskRecord


class Notifier:
    def __init__(self, console, channel=None):
        self._console = console
        self._channel = channel
        self._lock = threading.Lock()

    def notify(self, task: TaskRecord):
        with self._lock:
            # Rich console is thread-safe
            self._console.print(
                f"\n[bold yellow]>> NEW TASK ARRIVED:[/bold yellow] "
                f"[[bold cyan]{task.id}[/bold cyan]] "
                f"[bold]{task.title}[/bold] "
                f"(priority {task.priority})"
            )
            if self._channel is not None:
                try:
                    self._channel.send(
                        f"📨 NEW TASK [{task.id}] Priority {task.priority}: {task.title}\n"
                        f"{task.description}"
                    )
                except Exception:
                    pass
