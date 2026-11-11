"""Bounded private-upload recovery. Does not delete ready or submitted model data."""

import asyncio

from app.core.config import Settings
from app.database.session import build_database
from app.intake.storage import LocalPrivateStorage
from app.services.uploads import cleanup_uploads


async def main() -> None:
    settings = Settings()
    engine, factory = build_database(settings)
    try:
        storage = LocalPrivateStorage(settings.storage_root)
        await storage.prepare()
        count = await cleanup_uploads(factory, storage, limit=100)
        print(f"Private upload recovery: {count} expired/delete-pending reservations removed.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
