from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.auth import router
from app.api.business import router as business_router
from app.api.intake import router as intake_router
from app.api.schemas import ErrorResponse
from app.core.config import Settings
from app.core.errors import AuthError
from app.database.session import build_database
from app.intake.storage import LocalPrivateStorage
from app.services.auth import consume_auth_rate_limit

logger = logging.getLogger("app.security")


def error_response(status: int, code: str, message: str) -> JSONResponse:
    headers = {"Cache-Control": "no-store", "Pragma": "no-cache"}
    if status == 429:
        headers["Retry-After"] = "60"
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(code=code, message=message, correlation_id=str(uuid4())).model_dump(),
        headers=headers,
    )


class AuthBodyLimitMiddleware:
    """Bound authentication and draft-command JSON buffering, including chunks."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not (
            scope.get("path") == "/api/v1/auth/telegram"
            or (
                scope.get("path", "").startswith("/api/v1/requests")
                and scope.get("method") in {"POST", "PATCH", "DELETE"}
            )
        ):
            await self.app(scope, receive, send)
            return
        # Model uploads are bounded incrementally by their quota-reserved stream.
        if scope.get("method") == "POST" and re.fullmatch(
            r"/api/v1/requests/[0-9a-fA-F-]{36}/files", scope.get("path", "")
        ):
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > 32_768:
                await error_response(413, "request_too_large", "Request is too large.")(
                    scope, receive, send
                )
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        consumed = False

        async def replay() -> Message:
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Uvicorn factory: `uvicorn app.main:create_app --factory`.

    Passing explicit Settings supports isolated tests/OpenAPI generation without
    loading a production credential or making import-time DB/network calls.
    """
    settings = settings or Settings()
    engine, factory = build_database(settings)
    storage = LocalPrivateStorage(settings.storage_root)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            try:
                async with engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
            except SQLAlchemyError:
                raise RuntimeError(
                    "PostgreSQL is unavailable; check private configuration and migrations."
                ) from None
            await storage.prepare()
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="3DPS Mini App API",
        version="0.4.0",
        lifespan=lifespan,
        docs_url=None if settings.app_env == "production" else "/docs",
        redoc_url=None,
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            415: {"model": ErrorResponse},
            413: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
        },
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = factory
    app.state.storage = storage

    @app.exception_handler(AuthError)
    async def handle_auth_error(_request: Request, error: AuthError) -> JSONResponse:
        logger.info("auth.request_rejected code=%s status=%s", error.code, error.status)
        return error_response(error.status, error.code, error.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        # Pydantic errors contain the rejected input. Never echo initData/tokens.
        return error_response(422, "validation_error", "The request format is invalid.")

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(_request: Request, _error: SQLAlchemyError) -> JSONResponse:
        logger.error("auth.database_unavailable")
        return error_response(
            503, "service_unavailable", "The service is unavailable. Please try again."
        )

    @app.middleware("http")
    async def security_boundary(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            auth_path = (
                request.url.path.startswith("/api/v1/auth/")
                or request.url.path == "/api/v1/owner/auth-check"
            )
            if auth_path:
                # Client address is the transport peer. Forwarded headers never
                # select an identity/rate bucket in application code.
                peer = request.client.host if request.client else "unknown"
                await consume_auth_rate_limit(
                    factory, settings, peer, login=request.url.path == "/api/v1/auth/telegram"
                )
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                if request.headers.get("origin") != settings.origin:
                    raise AuthError(403, "origin_invalid", "Open this action from the Mini App.")
                if (
                    request.url.path == "/api/v1/auth/telegram"
                    and request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    != "application/json"
                ):
                    raise AuthError(415, "json_required", "Authentication requires a JSON request.")
            response = await call_next(request)
        except AuthError as error:
            logger.info("auth.request_rejected code=%s status=%s", error.code, error.status)
            response = error_response(error.status, error.code, error.message)
        except SQLAlchemyError:
            logger.error("auth.database_unavailable")
            response = error_response(
                503, "service_unavailable", "The service is unavailable. Please try again."
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    allowed_hosts = [urlsplit(settings.origin).hostname or "localhost"]
    if settings.app_env in {"development", "test"}:
        allowed_hosts.extend(["localhost", "127.0.0.1", "[::1]"])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts, www_redirect=False)
    app.add_middleware(AuthBodyLimitMiddleware)
    app.include_router(router)
    app.include_router(business_router)
    app.include_router(intake_router)
    return app
