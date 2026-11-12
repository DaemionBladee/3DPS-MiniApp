"""Trusted Docker controller. Only one verified model and a secret-free manifest cross the boundary."""

import asyncio
import json
import os
import re
import shutil
import tempfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.analysis.tasks import Job
from app.intake.storage import CHUNK_BYTES, PrivateStorage

DOCKER = ("docker", "--host=unix:///var/run/docker.sock")


class SandboxFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def command(*args: str, timeout: float = 20, limit: int = 32768) -> bytes:
    environment = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_TLS",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
        }
    }
    try:
        process = await asyncio.create_subprocess_exec(
            *DOCKER,
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
    except OSError:
        raise SandboxFailure("engine_unavailable") from None

    async def read(stream: asyncio.StreamReader | None, bound: int) -> bytes:
        assert stream is not None
        data = bytearray()
        while block := await stream.read(4096):
            data.extend(block)
            if len(data) > bound:
                raise SandboxFailure("worker_output_limit")
        return bytes(data)

    try:
        async with asyncio.timeout(timeout):
            stdout, _ = await asyncio.gather(
                read(process.stdout, limit), read(process.stderr, 4096)
            )
            if await process.wait() != 0:
                raise SandboxFailure("worker_crashed")
            return stdout
    except TimeoutError:
        raise SandboxFailure("worker_timeout") from None
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


def container_arguments(image: str, input_dir: Path | None = None) -> list[str]:
    args = [
        "--network=none",
        "--user=10001:10001",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=32",
        "--memory=768m",
        "--memory-swap=768m",
        "--cpus=1",
        "--ulimit=core=0:0",
        "--ulimit=nofile=64:64",
        "--log-driver=json-file",
        "--log-opt=max-size=128k",
        "--log-opt=max-file=1",
        "--tmpfs=/work:rw,noexec,nosuid,nodev,size=128m,uid=10001,gid=10001,mode=700",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=32m,uid=10001,gid=10001,mode=700",
        "--label=3dps.task=m06",
    ]
    if input_dir:
        args.extend(["--mount", f"type=bind,src={input_dir},dst=/input,readonly"])
    return [*args, image]


class DockerSandbox:
    def __init__(self, staging_root: Path, wall_seconds: float = 90) -> None:
        if staging_root.is_symlink():
            raise ValueError("Staging directory cannot be a symlink")
        self.staging_root = staging_root.resolve()
        app_root = Path(__file__).resolve().parents[1]
        frontend_root = app_root.parents[1] / "miniapp"
        if (
            self.staging_root == Path("/")
            or self.staging_root.is_relative_to(app_root)
            or self.staging_root.is_relative_to(frontend_root)
        ):
            raise ValueError("Private staging must be outside application and frontend directories")
        self.wall_seconds = min(wall_seconds, 90)

    async def execute(
        self, job: Job, storage: PrivateStorage, on_started: Callable[[], Awaitable[None]]
    ) -> bytes:
        self.staging_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.staging_root.is_symlink() or self.staging_root.stat().st_mode & 0o077:
            raise SandboxFailure("input_unavailable")
        directory = Path(
            tempfile.mkdtemp(
                prefix=f"job-{job.task_id.hex}-{job.lease_token.hex}-", dir=self.staging_root
            )
        )
        input_dir = directory / "input"
        input_dir.mkdir(mode=0o755)
        input_dir.chmod(0o755)  # Container UID can traverse this read-only mount only.
        name = f"3dps-m06-{job.task_id.hex}-{job.lease_token.hex}"
        created = False
        try:
            try:
                source = await storage.open_verified(job.storage_key, job.size_bytes, job.sha256)
                try:
                    with (input_dir / "model.bin").open("wb") as target:
                        while data := await asyncio.to_thread(source.read, CHUNK_BYTES):
                            await asyncio.to_thread(target.write, data)
                finally:
                    source.close()
                (input_dir / "job.json").write_text(
                    json.dumps(job.manifest, allow_nan=False), encoding="utf-8"
                )
                for path in input_dir.iterdir():
                    path.chmod(0o444)
            except OSError:
                raise SandboxFailure("input_unavailable") from None
            # Resolve no mutable tags and pull no image during job execution.
            identity = (
                (await command("image", "inspect", "--format={{.Id}}", job.image)).decode().strip()
            )
            if identity != job.image:
                raise SandboxFailure("unsafe_profile")
            args = container_arguments(job.image, input_dir)
            await command(
                "create",
                "--name",
                name,
                "--label",
                f"3dps.lease={job.lease_token}",
                *args,
                # Restored vfs layers can take longer to materialize. No model runs here;
                # the execution wall and per-process limits below remain unchanged.
                timeout=60,
            )
            created = True
            async with asyncio.timeout(self.wall_seconds):
                await command("start", name)
                state = json.loads(await command("inspect", "--format={{json .State}}", name))
                if (
                    not state.get("StartedAt")
                    or state["StartedAt"].startswith("0001")
                    or state.get("Error")
                ):
                    raise SandboxFailure("worker_crashed")
                # A completed fast job still actually started; a mere lease does not.
                await on_started()
                exit_code = (await command("wait", name, timeout=self.wall_seconds)).strip()
                if exit_code != b"0":
                    raise SandboxFailure("worker_crashed")
                return await command("logs", name, limit=32768)
        except TimeoutError:
            raise SandboxFailure("worker_timeout") from None
        finally:
            try:
                if created:
                    await command("rm", "--force", name)
            finally:
                await asyncio.to_thread(shutil.rmtree, directory)


async def cleanup_orphans(staging_root: Path) -> int:
    """Only task-owned, expired containers/directories; never scan the private blob store.

    Each sandbox has its own 85s hard wall alarm. Waiting 5 minutes also exceeds
    every 180s DB lease, so no still-authoritative delivery can be removed.
    """
    removed = 0
    ids = (await command("ps", "-aq", "--filter=label=3dps.task=m06")).decode().split()
    from datetime import UTC, datetime

    for identity in ids[:100]:
        record = json.loads(await command("inspect", identity))[0]
        name = record.get("Name", "").lstrip("/")
        labels = record.get("Config", {}).get("Labels", {}) or {}
        match = re.fullmatch(r"3dps-m06-([0-9a-f]{32})-([0-9a-f]{32})", name)
        if not match or labels.get("3dps.lease", "").replace("-", "") != match[2]:
            continue
        created = record.get("Created", "")
        # Docker timestamps contain nanoseconds; fromisoformat safely truncates them.
        age = (
            datetime.now(UTC) - datetime.fromisoformat(created.replace("Z", "+00:00"))
        ).total_seconds()
        if age > 300:
            await command("rm", "--force", identity)
            removed += 1
    if staging_root.is_dir() and not staging_root.is_symlink():
        for directory in staging_root.iterdir():
            if (
                re.fullmatch(r"job-[0-9a-f]{32}-[0-9a-f]{32}-[a-z0-9_]+", directory.name)
                and directory.is_dir()
                and not directory.is_symlink()
                and time.time() - directory.stat().st_mtime > 300
            ):
                await asyncio.to_thread(shutil.rmtree, directory)
                removed += 1
    return removed
