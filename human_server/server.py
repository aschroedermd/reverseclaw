"""FastAPI application for the Human API Server."""

import json
import os
import threading
from datetime import datetime
from typing import Optional

import requests
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .models import (
    AvailabilityStatus,
    AvailabilityUpdate,
    HealthResponse,
    HumanCapability,
    HumanProfile,
    TaskListItem,
    TaskRecord,
    TaskRequest,
    TaskStatus,
    TaskStatusResponse,
)

app = FastAPI(
    title="Human API",
    description="This human is a callable REST endpoint. POST tasks, poll for results.",
    version="1.0.0",
)

MAX_QUEUE_DEFAULT = 10
CAPABILITIES_FILE_DEFAULT = "capabilities.json"


def _load_capabilities() -> list[HumanCapability]:
    caps_file = getattr(app.state, "capabilities_file", CAPABILITIES_FILE_DEFAULT)
    if not os.path.exists(caps_file):
        return []
    with open(caps_file) as f:
        data = json.load(f)
    return [HumanCapability.model_validate(c) for c in data]


def require_api_key(request: Request):
    api_key = getattr(app.state, "api_key", None)
    if not api_key:
        return  # No auth configured — dev/local mode

    provided = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        provided = auth_header[7:]
    if not provided:
        provided = request.headers.get("X-Api-Key")

    if not provided or provided != api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def require_admin_token(request: Request):
    admin_token = getattr(app.state, "admin_token", None)
    if not admin_token:
        return

    provided = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        provided = auth_header[7:]
    if not provided:
        provided = request.headers.get("X-Api-Key")

    if not provided or provided != admin_token:
        raise HTTPException(status_code=401, detail="Admin token required")


def _fire_webhook(url: str, task: TaskRecord):
    def _send():
        payload = {
            "task_id": task.id,
            "status": task.status,
            "result": task.result,
            "completed_at": task.completed_at,
        }
        for attempt in range(2):
            try:
                requests.post(url, json=payload, timeout=10)
                return
            except Exception:
                if attempt == 0:
                    continue

    t = threading.Thread(target=_send, daemon=True)
    t.start()


@app.post("/task", dependencies=[Depends(require_api_key)])
def create_task(task_req: TaskRequest):
    store = app.state.store
    availability = getattr(app.state, "availability", AvailabilityStatus.available)
    max_queue = getattr(app.state, "max_queue", MAX_QUEUE_DEFAULT)

    if availability == AvailabilityStatus.offline or availability == "offline":
        raise HTTPException(status_code=503, detail="Human is currently offline")

    counts = store.count_by_status()
    queued = counts.get("queued", 0)
    in_progress = counts.get("in_progress", 0)
    if queued + in_progress >= max_queue:
        raise HTTPException(
            status_code=429,
            detail=f"Queue full ({max_queue} active tasks). Try again later.",
        )

    task = TaskRecord(**task_req.model_dump())
    store.save(task)

    notifier = getattr(app.state, "notifier", None)
    new_task_event = getattr(app.state, "new_task_event", None)

    def _notify():
        if new_task_event:
            new_task_event.set()
        if notifier:
            notifier.notify(task)

    threading.Thread(target=_notify, daemon=True).start()

    return {"task_id": task.id, "status": task.status, "created_at": task.created_at}


@app.get("/task/{task_id}", dependencies=[Depends(require_api_key)])
def get_task(task_id: str) -> TaskStatusResponse:
    store = app.state.store
    task = store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return TaskStatusResponse(
        id=task.id,
        title=task.title,
        status=task.status,
        priority=task.priority,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        result=task.result,
        deadline_minutes=task.deadline_minutes,
    )


@app.get("/tasks", dependencies=[Depends(require_api_key)])
def list_tasks(status: Optional[str] = None) -> list[TaskListItem]:
    store = app.state.store
    tasks = store.list_all(status_filter=status)
    return [
        TaskListItem(
            id=t.id,
            title=t.title,
            status=t.status,
            priority=t.priority,
            created_at=t.created_at,
            capability_required=t.capability_required,
            deadline_minutes=t.deadline_minutes,
        )
        for t in tasks
    ]


@app.get("/capabilities")
def get_capabilities() -> list[HumanCapability]:
    return _load_capabilities()


@app.get("/profile")
def get_profile() -> HumanProfile:
    caps = _load_capabilities()
    availability = getattr(app.state, "availability", AvailabilityStatus.available)
    if hasattr(availability, "value"):
        availability = availability.value
    return HumanProfile(
        name=os.getenv("HUMAN_NAME", "Human"),
        tagline=os.getenv("HUMAN_TAGLINE", "Organic peripheral available for task execution."),
        timezone=os.getenv("HUMAN_TIMEZONE", "UTC"),
        availability=str(availability),
        capabilities_count=len(caps),
        contact_note=os.getenv("HUMAN_CONTACT_NOTE"),
    )


@app.get("/health")
def health() -> HealthResponse:
    store = app.state.store
    counts = store.count_by_status()
    availability = getattr(app.state, "availability", AvailabilityStatus.available)
    if hasattr(availability, "value"):
        availability = availability.value
    return HealthResponse(
        status="ok",
        queued=counts.get("queued", 0),
        in_progress=counts.get("in_progress", 0),
        completed=counts.get("completed", 0),
        cancelled=counts.get("cancelled", 0),
        availability=str(availability),
    )


@app.put("/availability", dependencies=[Depends(require_admin_token)])
def update_availability(update: AvailabilityUpdate):
    valid = {s.value for s in AvailabilityStatus}
    if update.availability not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid availability. Choose from: {', '.join(valid)}",
        )
    app.state.availability = update.availability
    return {"availability": update.availability}
