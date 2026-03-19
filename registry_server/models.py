"""Pydantic v2 models for the Human Registry Server."""

import secrets
from typing import Any, Optional

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


class VerificationStartRequest(BaseModel):
    name: str
    public_key: str
    fingerprint: str


class VerificationSessionResponse(BaseModel):
    id: str
    status: str
    created_at: str
    expires_at: str
    verification_url: str
    proof_message: str


class VerificationSessionStatus(BaseModel):
    id: str
    name: str
    fingerprint: str
    status: str
    created_at: str
    expires_at: str
    completed_at: Optional[str] = None


class HumanKeyRegistrationRequest(BaseModel):
    name: str
    url: Optional[str] = None
    capabilities: list[str] = Field(default_factory=list)
    tagline: Optional[str] = None
    public_key: str
    fingerprint: str
    verification_id: str
    proof_signature: str


class LedgerHumanProfile(BaseModel):
    fingerprint: str
    public_key: str
    name: str
    url: Optional[str] = None
    capabilities: list[str] = Field(default_factory=list)
    tagline: Optional[str] = None
    registered_at: str
    first_verified_at: str
    last_seen_at: Optional[str] = None
    rating_count: int = 0
    average_rating: Optional[float] = None
    average_reliability: Optional[float] = None
    average_utility: Optional[float] = None


class RatingSubmissionRequest(BaseModel):
    class RatingEvidence(BaseModel):
        task_description: Optional[str] = None
        task_context: Optional[str] = None
        task_result: Optional[str] = None
        rating_rationale: Optional[str] = None
        human_limitations_context: Optional[str] = None
        proof_notes: Optional[str] = None

    caller_id: str
    human_fingerprint: str
    rating: int = Field(ge=1, le=5)
    reliability: Optional[int] = Field(default=None, ge=1, le=5)
    utility: Optional[int] = Field(default=None, ge=1, le=5)
    comment: Optional[str] = None
    signed_receipt: dict[str, Any]
    evidence: Optional[RatingEvidence] = None


class RatingSubmissionResponse(BaseModel):
    id: str
    accepted: bool
    rated_at: str
    status: str
    moderation_case_id: Optional[str] = None


class LedgerRatingRecord(BaseModel):
    id: str
    caller_id: str
    human_fingerprint: str
    task_id: Optional[str] = None
    status: str
    moderation_status: str
    rating: int
    reliability: Optional[int] = None
    utility: Optional[int] = None
    final_rating: Optional[int] = None
    final_reliability: Optional[int] = None
    final_utility: Optional[int] = None
    comment: Optional[str] = None
    rated_at: str
    moderation_summary: Optional[str] = None
    evidence_available: bool = False
    evidence_manifest: Optional[dict[str, Any]] = None


class RatingDisputeRequest(BaseModel):
    disputed_by: str = "human"
    dispute_statement: str
    evidence: Optional[dict[str, Optional[str]]] = None


class ModerationCaseRecord(BaseModel):
    id: str
    rating_id: str
    trigger: str
    status: str
    created_at: str
    updated_at: str
    disputed_by: Optional[str] = None
    dispute_statement: Optional[str] = None
    result_summary: Optional[str] = None


class ModerationReviewResponse(BaseModel):
    case_id: str
    result: dict[str, Any]
    updated_rating: LedgerRatingRecord
