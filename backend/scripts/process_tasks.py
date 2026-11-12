"""Run outside the API container; trusted host needs DB/storage/Docker, sandbox gets none."""

import argparse
import asyncio
import json
import logging
import re
import signal
from pathlib import Path
from uuid import uuid4

from app.analysis.orchestrator import process_one
from app.analysis.registry import seed_profiles
from app.analysis.sandbox import DockerSandbox, cleanup_orphans, command, container_arguments
from app.core.config import Settings
from app.database.session import build_database
from app.intake.storage import LocalPrivateStorage


async def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-root", type=Path, default=Path(".local/analysis_jobs"))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--seed-image", help="Explicitly approve immutable local worker image ID")
    parser.add_argument("--profile-revision", type=int, default=1)
    args = parser.parse_args()
    settings = Settings()
    engine, factory = build_database(settings)
    try:
        if args.seed_image:
            if not re.fullmatch("sha256:[0-9a-f]{64}", args.seed_image):
                raise ValueError("Approve an immutable local image ID, never a tag")
            output = await command(
                "run", "--rm", *container_arguments(args.seed_image), "--probe=base"
            )
            probe = json.loads(output)
            if probe.get("engine_version") != "2.5.0+UNKNOWN" or "probe" not in probe:
                raise RuntimeError("Worker isolation probe failed")
            async with factory() as db, db.begin():
                ids = await seed_profiles(
                    db, args.seed_image, probe["executable_sha256"], args.profile_revision
                )
            print(
                f"Approved {len(ids)} uncalibrated simulation profiles at revision {args.profile_revision}."
            )
            return
        storage = LocalPrivateStorage(settings.storage_root)
        await storage.prepare()
        sandbox = DockerSandbox(args.staging_root)
        owner = f"orchestrator-{uuid4()}"
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        while not stop.is_set():
            await cleanup_orphans(sandbox.staging_root)
            processed = await process_one(factory, storage, sandbox, owner)
            if args.once:
                break
            if not processed:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=3)
                except TimeoutError:
                    pass
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(run())
