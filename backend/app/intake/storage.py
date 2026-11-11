"""Private, replaceable blob adapter. Opaque keys never cross the HTTP boundary."""

import asyncio
import hashlib
import os
import re
import stat
from collections.abc import AsyncIterator
from pathlib import Path
from typing import BinaryIO, Protocol

from app.core.errors import AuthError

CHUNK_BYTES = 64 * 1024


class PrivateStorage(Protocol):
    async def prepare(self) -> None: ...
    async def stage(
        self, key: str, chunks: AsyncIterator[bytes], expected_size: int, expected_hash: str
    ) -> Path: ...
    async def promote(self, key: str) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def verify(self, key: str, size: int, checksum: str) -> None: ...
    async def open_verified(self, key: str, size: int, checksum: str) -> BinaryIO: ...


async def check_stream(
    chunks: AsyncIterator[bytes], size: int, checksum: str, output: BinaryIO | None = None
) -> None:
    received = 0
    digest = hashlib.sha256()
    async for block in chunks:
        received += len(block)
        if received > size:
            raise AuthError(413, "upload_size_exceeded", "The upload exceeds its declared size.")
        for position in range(0, len(block), CHUNK_BYTES):
            chunk = block[position : position + CHUNK_BYTES]
            digest.update(chunk)
            if output is not None:
                await asyncio.to_thread(output.write, chunk)
    if received != size:
        raise AuthError(422, "upload_incomplete", "The upload did not complete.")
    if digest.hexdigest() != checksum:
        raise AuthError(422, "upload_checksum_mismatch", "The upload checksum does not match.")


class LocalPrivateStorage:
    def __init__(self, root: Path):
        self.root = root

    async def prepare(self) -> None:
        def create() -> None:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            if self.root.is_symlink():
                raise OSError("Private storage cannot be a symlink")
            self.root.chmod(0o700)
            for area in ["incoming", "quarantine", "ready"]:
                path = self.root / area
                path.mkdir(mode=0o700, exist_ok=True)
                if path.is_symlink() or not path.is_dir():
                    raise OSError("Invalid private storage directory")
                path.chmod(0o700)

        await asyncio.to_thread(create)

    def path(self, area: str, key: str) -> Path:
        if area not in {"incoming", "quarantine", "ready"} or not re.fullmatch(
            r"[0-9a-f]{32}", key
        ):
            raise ValueError("Invalid internal blob key")
        return self.root / area / key

    def sync_directory(self, area: str) -> None:
        descriptor = os.open(self.root / area, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    async def stage(
        self, key: str, chunks: AsyncIterator[bytes], expected_size: int, expected_hash: str
    ) -> Path:
        path = self.path("incoming", key)
        descriptor = await asyncio.to_thread(
            os.open, path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "wb") as output:
            await check_stream(chunks, expected_size, expected_hash, output)
            await asyncio.to_thread(output.flush)
            await asyncio.to_thread(os.fsync, output.fileno())
        destination = self.path("quarantine", key)
        await asyncio.to_thread(os.replace, path, destination)
        await asyncio.to_thread(self.sync_directory, "quarantine")
        return destination

    async def promote(self, key: str) -> None:
        await asyncio.to_thread(os.replace, self.path("quarantine", key), self.path("ready", key))
        await asyncio.to_thread(self.sync_directory, "ready")

    async def delete(self, key: str) -> None:
        for area in ["incoming", "quarantine", "ready"]:
            await asyncio.to_thread(self.path(area, key).unlink, missing_ok=True)
            await asyncio.to_thread(self.sync_directory, area)

    def _open(self, key: str, size: int, checksum: str) -> BinaryIO:
        descriptor = os.open(self.path("ready", key), os.O_RDONLY | os.O_NOFOLLOW)
        handle = os.fdopen(descriptor, "rb")
        try:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != size:
                raise OSError("Stored blob size mismatch")
            digest = hashlib.sha256()
            while chunk := handle.read(CHUNK_BYTES):
                digest.update(chunk)
            if digest.hexdigest() != checksum:
                raise OSError("Stored blob checksum mismatch")
            handle.seek(0)
            return handle
        except BaseException:
            handle.close()
            raise

    async def open_verified(self, key: str, size: int, checksum: str) -> BinaryIO:
        return await asyncio.to_thread(self._open, key, size, checksum)

    async def verify(self, key: str, size: int, checksum: str) -> None:
        handle = await self.open_verified(key, size, checksum)
        await asyncio.to_thread(handle.close)
