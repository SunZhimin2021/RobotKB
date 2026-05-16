from __future__ import annotations

import asyncio
import io
from typing import Any

from minio import Minio
from minio.error import S3Error

from common.exceptions import StorageUnavailable


class MinioClient:
    """Async wrapper around the synchronous minio.Minio client."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
    ) -> None:
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._bucket = bucket
        self._loop_getter = asyncio.get_event_loop

    # ── helpers ────────────────────────────────────────────────────────────────

    def _run_sync(self, func, *args: Any, **kwargs: Any):
        """Run a synchronous callable in the default executor."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, lambda: func(*args, **kwargs))

    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    # ── public API ─────────────────────────────────────────────────────────────

    async def upload(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload bytes to MinIO and return the object_name."""
        def _upload():
            self._ensure_bucket()
            self._client.put_object(
                self._bucket,
                object_name,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
        try:
            await asyncio.get_event_loop().run_in_executor(None, _upload)
            return object_name
        except S3Error as exc:
            raise StorageUnavailable(f"MinIO upload failed: {exc}") from exc

    async def download(self, object_name: str) -> bytes:
        """Download an object and return its raw bytes."""
        def _download() -> bytes:
            response = self._client.get_object(self._bucket, object_name)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _download)
        except S3Error as exc:
            raise StorageUnavailable(f"MinIO download failed: {exc}") from exc

    async def delete(self, object_name: str) -> None:
        """Remove an object from the bucket."""
        def _delete():
            self._client.remove_object(self._bucket, object_name)

        try:
            await asyncio.get_event_loop().run_in_executor(None, _delete)
        except S3Error as exc:
            raise StorageUnavailable(f"MinIO delete failed: {exc}") from exc

    async def exists(self, object_name: str) -> bool:
        """Return True if the object exists in the bucket."""
        def _exists() -> bool:
            try:
                self._client.stat_object(self._bucket, object_name)
                return True
            except S3Error:
                return False

        return await asyncio.get_event_loop().run_in_executor(None, _exists)
