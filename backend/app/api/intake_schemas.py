from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.business_schemas import BusinessInput, CreateRequest, RequestResponse

MaterialKey = Literal["dev-pla", "dev-petg", "not-sure"]
ColorKey = Literal["dev-white", "dev-black", "not-sure"]
QualityKey = Literal["dev-standard", "dev-fine", "not-sure"]
UnitKey = Literal["mm", "cm", "inch", "um", "ft", "m"]


class ItemSpecification(BusinessInput):
    description: str = Field(default="", max_length=300)
    quantity: int = Field(default=1, ge=1, le=1000)
    material_key: MaterialKey | None = None
    color_key: ColorKey | None = None
    quality_key: QualityKey | None = None
    unit_key: UnitKey = "mm"
    unit_confirmed: bool = False
    special_requirements: str = Field(default="", max_length=2000)

    required_by: Annotated[date, Field(strict=False)] | None = None
    safety_critical: bool | None = None
    unusual_tolerance: bool | None = None
    requirements_confirmed: bool = False

    @field_validator("required_by", mode="before")
    @classmethod
    def iso_deadline(cls, value: Any) -> Any:
        if value is None or isinstance(value, date):
            return value
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError("Use a complete ISO date")
        return value

    dimension_x_mm: float | None = Field(default=None, gt=0, le=1000000, allow_inf_nan=False)
    dimension_y_mm: float | None = Field(default=None, gt=0, le=1000000, allow_inf_nan=False)
    dimension_z_mm: float | None = Field(default=None, gt=0, le=1000000, allow_inf_nan=False)
    dimension_tolerance_mm: float = Field(default=0.5, gt=0, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def complete_dimensions(self) -> "ItemSpecification":
        values = [self.dimension_x_mm, self.dimension_y_mm, self.dimension_z_mm]
        if any(v is not None for v in values) and any(v is None for v in values):
            raise ValueError("Confirm all three dimensions, or units alone")
        return self

    @field_validator("description", "special_requirements")
    @classmethod
    def safe_text(cls, value: str) -> str:
        return CreateRequest.safe_notes(value)


class CreateItem(BusinessInput):
    expected_version: int = Field(ge=1)
    specification: ItemSpecification = Field(default_factory=ItemSpecification)


class UpdateItem(CreateItem):
    pass


class VersionCommand(BusinessInput):
    expected_version: int = Field(ge=1)


class FileMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_id: UUID
    request_item_id: UUID | None
    purpose: Literal["model", "design_reference", "design_proof", "design_manufacturing"] = "model"
    download_allowed: bool = True
    request_revision: int
    original_name: str
    size_bytes: int
    sha256: str | None
    format: str | None
    format_details: dict[str, Any]
    validation_status: Literal["pending", "validated", "rejected", "removed"]
    storage_state: Literal["receiving", "ready", "delete_pending", "deleted"]
    failure_code: str | None


class ItemDetail(BaseModel):
    id: UUID
    request_revision: int
    specification: ItemSpecification
    model_file: FileMetadata | None
    latest_upload: FileMetadata | None


class IntakeRequest(RequestResponse):
    spec_schema_version: int
    fulfillment_method: Literal["pickup", "delivery"]
    fulfillment_notes: str
    submitted_revision: int | None
    submitted_at: datetime | None
    submitted_spec: dict[str, Any] | None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    uploaded_file_id: UUID
    request_revision: int
    spec_sha256: str
    kind: Literal["model_analysis"]
    state: Literal["pending", "leased", "succeeded", "failed", "superseded"]
    attempts: int = 0
    error_code: str | None = None
    retryable: bool = False
    started_at: datetime | None = None


class IntakeDetail(BaseModel):
    request: IntakeRequest
    items: list[ItemDetail]
    tasks: list[TaskResponse]
    customer_display_name: str


class AnalysisStatus(BaseModel):
    state: Literal[
        "not_submitted",
        "pending",
        "processing",
        "completed",
        "manual_review",
        "needs_clarification",
        "failed",
        "superseded",
    ]
    tasks: list[TaskResponse]
    processing_available: bool = False


class CatalogOption(BaseModel):
    key: str
    label: str


class MaterialOption(CatalogOption):
    color_keys: list[str]


class PrintingOptions(BaseModel):
    catalog_version: Literal["development-v1"] = "development-v1"
    simulation_only: Literal[True] = True
    notice: str = "Development options only. Stock and printer capability are not configured for commercial fulfillment."
    materials: list[MaterialOption]
    colors: list[CatalogOption]
    qualities: list[CatalogOption]
    units: list[CatalogOption]
    max_file_bytes: int
    max_request_files: int
