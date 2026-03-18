"""Pydantic v2 models for the Human API Server."""

import secrets
from datetime import datetime
from enum import Enum
from typing import Optional

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


class TaskListItem(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    title: str
    status: str
    priority: int
    created_at: str
    capability_required: Optional[str] = None
    deadline_minutes: Optional[int] = None


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
