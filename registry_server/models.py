"""Pydantic v2 models for the Human Registry Server."""

import secrets
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    name: str
    url: str
    capabilities: list[str] = Field(default_factory=list)
    tagline: Optional[str] = None


class RegistryEntry(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(default_factory=lambda: secrets.token_hex(4))
    token: str = Field(default_factory=lambda: secrets.token_hex(16))
    name: str
    url: str
    capabilities: list[str] = Field(default_factory=list)
    tagline: Optional[str] = None
    registered_at: str
    last_heartbeat: str
    availability: str = "available"


class HeartbeatRequest(BaseModel):
    token: str
    availability: Optional[str] = None


class RegistrationResponse(BaseModel):
    id: str
    token: str
    message: str


class HumanListing(BaseModel):
    id: str
    name: str
    url: str
    capabilities: list[str]
    tagline: Optional[str]
    availability: str
    registered_at: str
    last_heartbeat: str
