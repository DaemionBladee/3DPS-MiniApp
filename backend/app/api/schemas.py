from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.database.models import Role


class TelegramLogin(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    init_data: str = Field(min_length=1, max_length=16_384)


class UserResponse(BaseModel):
    id: UUID
    telegram_id: str
    display_name: str
    role: Role


class AuthResponse(BaseModel):
    user: UserResponse
    capabilities: list[str]
    csrf_token: str
    environment: Literal["simulation"] = "simulation"


class CsrfResponse(BaseModel):
    csrf_token: str


class StatusResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: list[str] = Field(default_factory=list)
    correlation_id: str
