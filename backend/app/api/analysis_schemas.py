"""Strict untrusted-worker output contract and deliberately safe public projections."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.business_schemas import BusinessInput
from app.api.intake_schemas import ItemSpecification, TaskResponse

Checksum = str


class WorkerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Dimensions(WorkerInput):
    x: float = Field(ge=0, le=1000000)
    y: float = Field(ge=0, le=1000000)
    z: float = Field(ge=0, le=1000000)


class Geometry(WorkerInput):
    format: Literal["stl", "obj", "3mf"]
    unit_key: Literal["mm", "cm", "inch", "um", "ft", "m"]
    declared_unit: str | None
    dimensions_mm: Dimensions
    volume_mm3: float | None = Field(ge=0, le=1e18)
    object_count: int = Field(ge=1, le=100000)
    component_count: int = Field(ge=1, le=300000)
    triangle_count: int = Field(ge=1, le=100000)
    watertight: bool
    boundary_edges: int = Field(ge=0, le=300000)
    nonmanifold_edges: int = Field(ge=0, le=300000)
    degenerate_faces: int = Field(ge=0, le=100000)
    duplicate_faces: int = Field(ge=0, le=100000)
    winding_errors: int = Field(ge=0, le=300000)
    build_volume_compatible: bool
    warnings: list[str] = Field(max_length=30)
    review_reasons: list[str] = Field(max_length=30)


class Estimate(WorkerInput):
    filament_g: float = Field(gt=0, le=1000000)
    print_seconds: int = Field(gt=0, le=31536000)
    support_g: None = None
    support_estimate_available: Literal[False] = False
    gcode_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    canonical_gcode_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    gcode_bytes: int = Field(gt=0, le=67108864)


class SandboxEvidence(WorkerInput):
    uid: Literal[10001]
    gid: Literal[10001]
    cap_eff: Literal["0000000000000000"]
    no_new_privs: Literal["1"]
    seccomp: Literal["2"]
    network_devices: list[Literal["lo"]] = Field(min_length=1, max_length=1)
    root_readonly: Literal[True]
    input_readonly: Literal[True]
    work_bytes: int = Field(gt=0, le=134217728)
    forbidden_environment: list[str] = Field(max_length=0)
    memory_limit: Literal[805306368]
    cpu_limit: Literal[60]
    pid_limit: Literal[32]
    file_limit: Literal[67108864]


class WorkerResult(WorkerInput):
    schema_version: Literal[1]
    task_id: str = Field(pattern="^[0-9a-f-]{36}$")
    lease_token: str = Field(pattern="^[0-9a-f-]{36}$")
    input_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    analyzer_version: Literal["3dps-geometry-1"]
    engine_version: str = Field(max_length=64)
    executable_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    geometry: Geometry
    outcome: Literal["estimated", "manual_review"]
    estimate: Estimate | None
    normalization_verified: bool = False
    sandbox: SandboxEvidence

    @model_validator(mode="after")
    def trustworthy(self) -> "WorkerResult":
        if self.outcome == "estimated":
            if (
                self.estimate is None
                or not self.normalization_verified
                or not self.geometry.watertight
                or not self.geometry.build_volume_compatible
                or self.geometry.review_reasons
                or self.geometry.volume_mm3 is None
            ):
                raise ValueError("Incomplete estimate")
        elif self.estimate is not None or not self.geometry.review_reasons:
            raise ValueError("Invalid manual review")
        import re

        if any(
            not re.fullmatch("[a-z_]{3,80}", code)
            for code in self.geometry.warnings + self.geometry.review_reasons
        ):
            raise ValueError("Unsafe diagnostic")
        return self


class SimulationProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    key: str
    version: int
    virtual_printer_model_id: UUID
    material_key: str
    quality_key: str
    configuration: dict[str, float | int | bool]
    config_sha256: str
    engine_version: str
    approval_status: Literal["approved"]
    active: bool
    calibrated: Literal[False]
    simulation_only: Literal[True]


class AnalysisResult(BaseModel):
    id: UUID
    task_id: UUID
    request_item_id: UUID
    uploaded_file_id: UUID
    request_revision: int
    spec_sha256: str
    input_sha256: str
    outcome: Literal["estimated", "manual_review"]
    geometry: Geometry
    estimate: Estimate | None
    profile: SimulationProfile
    profile_snapshot: dict[str, object]
    engine_version: str
    executable_sha256: str
    worker_image: str
    quantity: int
    submitted_specification: ItemSpecification
    special_requirements: bool
    simulation_only: Literal[True] = True
    notice: Literal["Simulation estimate — not a final quotation."] = (
        "Simulation estimate — not a final quotation."
    )


class AnalysisResults(BaseModel):
    items: list[AnalysisResult]


class OwnerTask(TaskResponse):
    request_id: UUID
    customer_id: UUID
    selected_profile_id: UUID | None
    max_attempts: int
    next_available_at: datetime
    completed_at: datetime | None
    special_requirements: bool


class TaskPage(BaseModel):
    items: list[OwnerTask]
    next_offset: int | None


class RetryTask(BusinessInput):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=8, max_length=500)
    profile_id: UUID | None = None


class RetryResponse(BaseModel):
    request_id: UUID
    task_id: UUID
    version: int
    state: Literal["pending"] = "pending"
