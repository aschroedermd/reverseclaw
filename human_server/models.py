"""Pydantic v2 models for the Human API Server."""

import secrets
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(str, Enum):
    queued = "queued"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class AvailabilityStatus(str, Enum):
    available = "available"
    busy = "busy"
    offline = "offline"


class TaskRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    title: str
    description: str
    context: Optional[str] = None
    task_tags: list[str] = Field(default_factory=list)
    estimated_effort_minutes: Optional[int] = Field(default=None, ge=1)
    estimated_cost_usd: Optional[float] = Field(default=None, ge=0)
    requires_purchase: bool = False
    requires_sensitive_data: bool = False
    requires_external_contact: bool = False
    requires_physical_presence: bool = False
    goal_id: Optional[str] = None
    goal_label: Optional[str] = None
    success_criteria: Optional[str] = None
    proof_required: bool = False
    capability_required: Optional[str] = None
    deadline_minutes: Optional[int] = None
    callback_url: Optional[str] = None
    caller_id: Optional[str] = None
    priority: int = Field(default=3, ge=1, le=5)


class TaskRecord(TaskRequest):
    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(default_factory=lambda: secrets.token_hex(4))
    status: str = TaskStatus.queued.value
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    signed_receipt: Optional[dict[str, Any]] = None


class HumanCapability(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    name: str
    description: str
    estimated_response_minutes: int
    examples: list[str] = Field(default_factory=list)
    price_per_task: Optional[float] = None


class HumanProfile(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    name: str
    tagline: str
    timezone: str
    availability: str
    capabilities_count: int
    contact_note: Optional[str] = None
    public_key: Optional[str] = None
    public_key_fingerprint: Optional[str] = None
    identity_created_at: Optional[str] = None
    boundaries_summary: Optional[str] = None


class HumanBoundaries(BaseModel):
    version: int = 1
    blocked_tags: list[str] = Field(default_factory=list)
    max_estimated_cost_usd: float = 0.0
    allow_purchases: bool = False
    allow_sensitive_data: bool = False
    allow_external_contact: bool = True
    allow_physical_presence: bool = True
    max_estimated_effort_minutes: int = 240
    notes: Optional[str] = None


class TaskStatusResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    title: str
    status: str
    priority: int
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    deadline_minutes: Optional[int] = None
    task_tags: list[str] = Field(default_factory=list)
    estimated_effort_minutes: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    goal_id: Optional[str] = None
    goal_label: Optional[str] = None
    success_criteria: Optional[str] = None
    proof_required: bool = False
    signed_receipt: Optional[dict[str, Any]] = None


class TaskListItem(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    title: str
    status: str
    priority: int
    created_at: str
    capability_required: Optional[str] = None
    deadline_minutes: Optional[int] = None
    task_tags: list[str] = Field(default_factory=list)
    goal_id: Optional[str] = None
    goal_label: Optional[str] = None
    proof_required: bool = False


class AvailabilityUpdate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    availability: str


class HealthResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    status: str
    queued: int
    in_progress: int
    completed: int
    cancelled: int
    availability: str
