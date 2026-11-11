from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.types import RequestStatus, ServiceType, StageKind


class BusinessInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CreateRequest(BusinessInput):
    service_type: ServiceType
    customer_notes: str = Field(default="", max_length=2000)

    @field_validator("customer_notes")
    @classmethod
    def safe_notes(cls, value: str) -> str:
        value.encode("utf-8", errors="strict")
        if "\x00" in value:
            raise ValueError("Invalid note text")
        return value


class DraftPatch(BusinessInput):
    expected_version: int = Field(ge=1)
    customer_notes: str = Field(max_length=2000)
    fulfillment_method: Literal["pickup", "delivery"] | None = None
    fulfillment_notes: str | None = Field(default=None, max_length=1000)

    @field_validator("customer_notes", "fulfillment_notes")
    @classmethod
    def safe_notes(cls, value: str | None) -> str | None:
        return CreateRequest.safe_notes(value) if value is not None else None


class RequestTransition(BusinessInput):
    expected_version: int = Field(ge=1)
    target: Literal["submitted", "cancelled"]
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def safe_reason(cls, value: str) -> str:
        value = CreateRequest.safe_notes(value).strip()
        if len(value) < 3:
            raise ValueError("A reason is required")
        return value


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    customer_id: UUID
    kind: ServiceType
    mode: Literal["simulation"]
    created_at: datetime


class RequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    service_project_id: UUID
    customer_id: UUID
    service_type: ServiceType
    stage_kind: StageKind
    source_design_version_id: UUID | None = None
    mode: Literal["simulation"]
    status: RequestStatus
    version: int
    revision: int
    canonical_spec_sha256: str
    customer_notes: str
    created_at: datetime
    updated_at: datetime


class ProjectRequestResponse(BaseModel):
    project: ProjectResponse
    request: RequestResponse


class RequestPage(BaseModel):
    items: list[RequestResponse]
    next_offset: int | None


class ProjectPage(BaseModel):
    items: list[ProjectResponse]
    next_offset: int | None
