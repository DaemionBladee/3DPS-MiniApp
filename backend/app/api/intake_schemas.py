from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    state: Literal["pending", "superseded"]


class IntakeDetail(BaseModel):
    request: IntakeRequest
    items: list[ItemDetail]
    tasks: list[TaskResponse]
    customer_display_name: str


class AnalysisStatus(BaseModel):
    state: Literal["not_submitted", "pending", "superseded"]
    tasks: list[TaskResponse]
    processing_available: Literal[False] = False


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
