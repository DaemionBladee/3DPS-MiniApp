from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.business_schemas import BusinessInput, CreateRequest, RequestResponse
from app.api.intake_schemas import FileMetadata, VersionCommand

ApiUUID = Annotated[UUID, Field(strict=False)]


class DesignBrief(BusinessInput):
    description: str = Field(default="", max_length=4000)
    intended_use: str = Field(default="", max_length=2000)
    dimensions: str = Field(default="", max_length=1000)
    units: Literal["mm", "cm", "inch", "not_sure"] = "mm"
    tolerances: str = Field(default="", max_length=1000)
    manufacturing_preferences: str = Field(default="", max_length=1000)
    desired_completion_date: str | None = None
    special_requirements: str = Field(default="", max_length=2000)
    delivery_kind: Literal["digital", "printing", "both"] = "digital"

    @field_validator("desired_completion_date")
    @classmethod
    def valid_date(cls, value: str | None) -> str | None:
        if value is not None and date.fromisoformat(value).isoformat() != value:
            raise ValueError("Use an ISO date")
        return value

    @field_validator(
        "description",
        "intended_use",
        "dimensions",
        "tolerances",
        "manufacturing_preferences",
        "special_requirements",
    )
    @classmethod
    def safe_text(cls, value: str) -> str:
        return CreateRequest.safe_notes(value)


class BriefCommand(VersionCommand):
    brief: DesignBrief


class DesignScope(BusinessInput):
    deliverables: str = Field(min_length=3, max_length=3000)
    permitted_revisions: int = Field(ge=0, le=20)
    exclusions: str = Field(default="", max_length=2000)
    includes_digital_delivery: bool

    @field_validator("deliverables", "exclusions")
    @classmethod
    def safe_text(cls, value: str) -> str:
        return CreateRequest.safe_notes(value)


class ScopeCommand(VersionCommand):
    @field_validator("reason")
    @classmethod
    def safe_text(cls, value: str) -> str:
        return CreateRequest.safe_notes(value)

    scope: DesignScope
    reason: str = Field(min_length=3, max_length=500)


class ScopeAgreement(VersionCommand):
    scope_id: ApiUUID


class SimulationFixture(VersionCommand):
    @field_validator("reason")
    @classmethod
    def safe_text(cls, value: str) -> str:
        return CreateRequest.safe_notes(value)

    confirm_simulation: Literal[True]
    reason: str = Field(min_length=3, max_length=500)


class PublishProof(VersionCommand):
    @field_validator("release_notes")
    @classmethod
    def safe_text(cls, value: str) -> str:
        return CreateRequest.safe_notes(value)

    preview_file_id: ApiUUID
    manufacturing_file_id: ApiUUID | None = None
    manufacturing_ready: bool = False
    release_notes: str = Field(min_length=3, max_length=2000)

    @model_validator(mode="after")
    def consistent_model(self) -> "PublishProof":
        if self.manufacturing_ready != (self.manufacturing_file_id is not None):
            raise ValueError("Manufacturing-ready proof needs a model")
        return self


class ReviewProof(VersionCommand):
    @field_validator("feedback")
    @classmethod
    def safe_text(cls, value: str) -> str:
        return CreateRequest.safe_notes(value)

    design_version_id: ApiUUID
    decision: Literal["approved", "changes_requested"]
    feedback: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def feedback_required(self) -> "ReviewProof":
        if self.decision == "changes_requested" and len(self.feedback.strip()) < 3:
            raise ValueError("Revision feedback is required")
        return self


class ConvertDesign(VersionCommand):
    design_version_id: ApiUUID


class ScopeResponse(BaseModel):
    id: ApiUUID
    number: int
    scope: DesignScope
    agreed: bool
    binding: Literal[False] = False


class DesignReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: ApiUUID
    design_version_id: ApiUUID
    decision: Literal["approved", "changes_requested"]
    feedback: str


class DesignVersionResponse(BaseModel):
    id: ApiUUID
    number: int
    scope_id: ApiUUID
    preview: FileMetadata
    manufacturing_file: FileMetadata | None
    manufacturing_ready: bool
    release_notes: str
    specification_sha256: str
    review: DesignReviewResponse | None


class DesignDetail(BaseModel):
    id: ApiUUID
    request: RequestResponse
    state: Literal[
        "draft",
        "brief_received",
        "scoping",
        "awaiting_payment",
        "designing",
        "customer_review",
        "approved",
    ]
    brief: DesignBrief
    scopes: list[ScopeResponse]
    approved_scope_id: ApiUUID | None
    versions: list[DesignVersionResponse]
    latest_version_id: ApiUUID | None
    approved_version_id: ApiUUID | None
    references: list[FileMetadata]
    working_files: list[FileMetadata]
    simulation_fixture: bool
    linked_print_request: RequestResponse | None
    linked_print_item_id: ApiUUID | None
    customer_display_name: str
    digital_release_available: Literal[False] = False
    notice: str = "Simulation only. Scope agreement and proof approval do not create a quotation, payment, live work authorization or digital delivery."


class RemoveReference(VersionCommand):
    file_id: ApiUUID


class DesignPage(BaseModel):
    items: list[DesignDetail]
    next_offset: int | None
