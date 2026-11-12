"""Separate trusted host process: SQL/storage access never enters the native sandbox."""

import json
from collections.abc import Awaitable, Callable
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analysis.sandbox import SandboxFailure
from app.analysis.tasks import Job, LeaseLost, claim, failed, publish, started
from app.intake.storage import PrivateStorage


class Sandbox(Protocol):
    async def execute(
        self, job: Job, storage: PrivateStorage, on_started: Callable[[], Awaitable[None]]
    ) -> bytes: ...


async def process_one(
    factory: async_sessionmaker[AsyncSession], storage: PrivateStorage, sandbox: Sandbox, owner: str
) -> bool:
    job = await claim(factory, owner)
    if job is None:
        return False
    try:
        output = await sandbox.execute(job, storage, lambda: started(factory, job))
        if len(output) > 32768:
            raise SandboxFailure("worker_output_limit")
        decoded = json.loads(output)
        if isinstance(decoded, dict) and set(decoded) == {"error", "retryable"}:
            # The orchestrator owns retry classification; ignore untrusted retry advice.
            await failed(factory, job, str(decoded["error"]))
        else:
            await publish(factory, job, output)
    except LeaseLost:
        return True  # Expired/duplicate results are deliberately discarded.
    except SandboxFailure as error:
        try:
            await failed(factory, job, error.code)
        except LeaseLost:
            pass
    except (ValueError, TypeError):
        try:
            await failed(factory, job, "output_verification_failed")
        except LeaseLost:
            pass
    except SQLAlchemyError:
        # Publication transaction rolled back, including audit/outbox. Retry only
        # if DB recovers and this lease is still current; otherwise expiry recovers it.
        try:
            await failed(factory, job, "publication_failed")
        except (SQLAlchemyError, LeaseLost):
            pass
        raise
    return True
