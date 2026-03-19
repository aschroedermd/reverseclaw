"""FastAPI application for the Human API Server."""

import ipaddress
import json
import os
import secrets
import socket
import threading
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import requests
from fastapi import Depends, FastAPI, HTTPException, Request

from .models import (
    AvailabilityStatus,
    AvailabilityUpdate,
    HealthResponse,
    HumanBoundaries,
    HumanCapability,
    HumanProfile,
    TaskListItem,
    TaskRecord,
    TaskRequest,
    TaskStatus,
    TaskStatusResponse,
)
from human_policy import BOUNDARIES_FILE_DEFAULT, load_boundaries, summarize_boundaries, validate_task_against_boundaries

app = FastAPI(
    title="Human API",
    description="This human is a callable REST endpoint. POST tasks, poll for results.",
    version="1.0.0",
)

MAX_QUEUE_DEFAULT = 10
MAX_QUEUE_PER_CALLER_DEFAULT = 3
CAPABILITIES_FILE_DEFAULT = "capabilities.json"


def _validate_callback_url(url: str) -> Optional[str]:
    """
    Returns an error string if the URL is unsafe, None if it's fine.
    Blocks non-HTTPS schemes and URLs that resolve to private/loopback IPs (SSRF).
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return "callback_url is not a valid URL"

    if parsed.scheme != "https":
        return "callback_url must use HTTPS (not http or other schemes)"

    hostname = parsed.hostname
    if not hostname:
        return "callback_url has no hostname"

    # Resolve hostname and reject private/reserved IP ranges
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(3)
        addrs = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return f"callback_url hostname '{hostname}' could not be resolved"
    finally:
        socket.setdefaulttimeout(old_timeout)

    for addr in addrs:
        try:
            ip = ipaddress.ip_address(addr[4][0])
            if any([
                ip.is_private,
                ip.is_loopback,
                ip.is_link_local,
                ip.is_reserved,
                ip.is_multicast,
                ip.is_unspecified,
            ]):
                return (
                    f"callback_url resolves to a private or reserved IP ({ip}). "
                    "Callbacks to internal network addresses are not permitted."
                )
        except ValueError:
            continue

    return None


def _load_capabilities() -> list[HumanCapability]:
    caps_file = getattr(app.state, "capabilities_file", CAPABILITIES_FILE_DEFAULT)
    if not os.path.exists(caps_file):
        return []
    with open(caps_file) as f:
        data = json.load(f)
    return [HumanCapability.model_validate(c) for c in data]


def _load_boundaries() -> dict:
    boundaries_file = getattr(app.state, "boundaries_file", BOUNDARIES_FILE_DEFAULT)
    return load_boundaries(boundaries_file)


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

    if not provided or not secrets.compare_digest(provided, api_key):
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

    if not provided or not secrets.compare_digest(provided, admin_token):
        raise HTTPException(status_code=401, detail="Admin token required")


def _fire_webhook(url: str, task: TaskRecord):
    def _send():
        payload = {
            "task_id": task.id,
            "status": task.status,
            "result": task.result,
            "completed_at": task.completed_at,
            "signed_receipt": task.signed_receipt,
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
    max_per_caller = getattr(app.state, "max_queue_per_caller", MAX_QUEUE_PER_CALLER_DEFAULT)
    boundaries = _load_boundaries()

    if availability == AvailabilityStatus.offline or availability == "offline":
        raise HTTPException(status_code=503, detail="Human is currently offline")

    violations = validate_task_against_boundaries(task_req, boundaries)
    if violations:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Task violates declared human boundaries",
                "violations": violations,
            },
        )

    # Validate callback_url before accepting the task (SSRF prevention)
    if task_req.callback_url:
        err = _validate_callback_url(task_req.callback_url)
        if err:
            raise HTTPException(status_code=422, detail=f"Invalid callback_url: {err}")

    counts = store.count_by_status()
    queued = counts.get("queued", 0)
    in_progress = counts.get("in_progress", 0)
    if queued + in_progress >= max_queue:
        raise HTTPException(
            status_code=429,
            detail=f"Queue full ({max_queue} active tasks). Try again later.",
        )

    # Per-caller queue limit (prevents one caller from monopolising the queue)
    if task_req.caller_id:
        caller_active = sum(
            1 for t in store.list_all()
            if t.caller_id == task_req.caller_id and t.status in ("queued", "in_progress")
        )
        if caller_active >= max_per_caller:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Caller '{task_req.caller_id}' already has {caller_active} active task(s). "
                    f"Limit per caller is {max_per_caller}. Complete or cancel existing tasks first."
                ),
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
        task_tags=task.task_tags,
        estimated_effort_minutes=task.estimated_effort_minutes,
        estimated_cost_usd=task.estimated_cost_usd,
        goal_id=task.goal_id,
        goal_label=task.goal_label,
        success_criteria=task.success_criteria,
        proof_required=task.proof_required,
        signed_receipt=task.signed_receipt,
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
            task_tags=t.task_tags,
            goal_id=t.goal_id,
            goal_label=t.goal_label,
            proof_required=t.proof_required,
        )
        for t in tasks
    ]


@app.get("/capabilities")
def get_capabilities() -> list[HumanCapability]:
    return _load_capabilities()


@app.get("/profile")
def get_profile() -> HumanProfile:
    caps = _load_capabilities()
    boundaries = _load_boundaries()
    availability = getattr(app.state, "availability", AvailabilityStatus.available)
    identity_meta = getattr(app.state, "identity_meta", {}) or {}
    if hasattr(availability, "value"):
        availability = availability.value
    return HumanProfile(
        name=os.getenv("HUMAN_NAME", "Human"),
        tagline=os.getenv("HUMAN_TAGLINE", "Organic peripheral available for task execution."),
        timezone=os.getenv("HUMAN_TIMEZONE", "UTC"),
        availability=str(availability),
        capabilities_count=len(caps),
        contact_note=os.getenv("HUMAN_CONTACT_NOTE"),
        public_key=identity_meta.get("public_key"),
        public_key_fingerprint=identity_meta.get("fingerprint"),
        identity_created_at=identity_meta.get("created_at"),
        boundaries_summary=summarize_boundaries(boundaries),
    )


@app.get("/boundaries")
def get_boundaries() -> HumanBoundaries:
    return HumanBoundaries.model_validate(_load_boundaries())


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
