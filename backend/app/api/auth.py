from __future__ import annotations

import hmac
import logging
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.schemas import AuthResponse, CsrfResponse, StatusResponse, TelegramLogin, UserResponse
from app.core.config import Settings
from app.core.errors import AuthError
from app.core.telegram import verify_init_data
from app.database.models import User
from app.services.auth import (
    Principal,
    csrf_token,
    establish_session,
    resolve_session,
    revoke_session,
)

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger("app.auth")


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)


SettingsDependency = Annotated[Settings, Depends(get_settings)]
FactoryDependency = Annotated[async_sessionmaker[AsyncSession], Depends(get_factory)]


def user_response(user: User) -> UserResponse:
    return UserResponse(id=user.id, telegram_id=str(user.telegram_id), display_name=user.display_name, role=user.role)


def auth_response(user: User, token: str, settings: Settings) -> AuthResponse:
    capabilities = ["auth.read_self", "auth.logout"]
    if user.role == "owner":
        capabilities.append("owner.auth_check")
    return AuthResponse(user=user_response(user), capabilities=capabilities, csrf_token=csrf_token(token, settings))


async def require_session(request: Request, settings: SettingsDependency, factory: FactoryDependency) -> Principal:
    return await resolve_session(factory, settings, request.cookies.get(settings.cookie_name))


PrincipalDependency = Annotated[Principal, Depends(require_session)]


@router.post("/auth/telegram", response_model=AuthResponse)
async def telegram_login(
    body: TelegramLogin, request: Request, response: Response, settings: SettingsDependency, factory: FactoryDependency
) -> AuthResponse:
    verified = verify_init_data(
        body.init_data,
        settings.bot_token.get_secret_value(),
        max_age_seconds=settings.auth_max_age_seconds,
        future_skew_seconds=settings.auth_future_skew_seconds,
    )
    previous = request.cookies.get(settings.cookie_name)
    if previous and (len(previous) != 43 or not previous.isascii()):
        previous = None
    user, token = await establish_session(factory, settings, verified, previous)
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )
    logger.info("auth.login_succeeded user_id=%s role=%s", user.id, user.role)
    return auth_response(user, token, settings)


@router.get("/auth/me", response_model=AuthResponse)
async def me(principal: PrincipalDependency, settings: SettingsDependency) -> AuthResponse:
    return auth_response(principal.user, principal.token, settings)


@router.get("/auth/csrf", response_model=CsrfResponse)
async def get_csrf(principal: PrincipalDependency, settings: SettingsDependency) -> CsrfResponse:
    return CsrfResponse(csrf_token=csrf_token(principal.token, settings))


@router.post("/auth/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    principal: PrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
) -> None:
    supplied = request.headers.get("x-csrf-token", "")
    expected = csrf_token(principal.token, settings)
    if len(supplied) != len(expected) or not supplied.isascii() or not hmac.compare_digest(supplied, expected):
        raise AuthError(403, "csrf_invalid", "Refresh the Mini App before trying again.")
    await revoke_session(factory, principal.session.id)
    response.delete_cookie(settings.cookie_name, path="/", secure=True, httponly=True, samesite="lax")
    logger.info("auth.logout_succeeded user_id=%s", principal.user.id)


@router.get("/owner/auth-check", response_model=StatusResponse)
async def owner_auth_check(principal: PrincipalDependency) -> StatusResponse:
    if principal.user.role != "owner":
        raise AuthError(403, "owner_required", "This action requires Owner access.")
    return StatusResponse()


@router.get("/auth/users/{user_id}", response_model=UserResponse)
async def own_auth_fixture(user_id: UUID, principal: PrincipalDependency) -> UserResponse:
    if user_id != principal.user.id:
        raise AuthError(404, "user_not_found", "This user could not be found.")
    return user_response(principal.user)


@router.get("/health", response_model=StatusResponse)
async def health() -> StatusResponse:
    return StatusResponse()
