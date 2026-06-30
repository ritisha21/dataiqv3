"""
backend/app/infrastructure/storage/minio_client.py
─────────────────────────────────────────────────
Thin wrapper around the MinIO SDK for storing versioned CSV snapshots
of database tables. Used by the extraction task and the drift detector.

Object key convention:
    {tenant_id}/{connection_id}/{table_name}/{timestamp}.csv

This keeps every snapshot, so the drift detector can always compare
the latest snapshot against the previous one.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from minio import Minio
from minio.error import S3Error

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class MinIOStorage:
    def __init__(self):
        self._client: Optional[Minio] = None
        self.bucket = settings.MINIO_BUCKET

    @property
    def client(self) -> Minio:
        if self._client is None:
            self._client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE,
            )
            self._ensure_bucket()
        return self._client

    def _ensure_bucket(self) -> None:
        try:
            if not self._client.bucket_exists(self.bucket):
                self._client.make_bucket(self.bucket)
                logger.info("minio_bucket_created", bucket=self.bucket)
        except S3Error as exc:
            logger.error("minio_bucket_check_failed", error=str(exc))
            raise

    # ─────────────────────────────────────────────────────────────────────────

    def _object_key(
        self,
        tenant_id: str,
        connection_id: str,
        table_name: str,
        timestamp: Optional[datetime] = None,
    ) -> str:
        ts = (timestamp or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
        return f"{tenant_id}/{connection_id}/{table_name}/{ts}.csv"

    def upload_csv(
        self,
        *,
        tenant_id: str,
        connection_id: str,
        table_name: str,
        csv_bytes: bytes,
    ) -> Dict[str, Any]:
        """
        Upload a CSV snapshot. Returns metadata including the object key
        and timestamp, so the caller can record it for drift comparison.
        """
        timestamp = datetime.now(timezone.utc)
        key = self._object_key(tenant_id, connection_id, table_name, timestamp)

        try:
            self.client.put_object(
                self.bucket,
                key,
                data=io.BytesIO(csv_bytes),
                length=len(csv_bytes),
                content_type="text/csv",
            )
            logger.info("minio_upload_success", key=key, size_bytes=len(csv_bytes))
            return {
                "object_key": key,
                "bucket": self.bucket,
                "timestamp": timestamp.isoformat(),
                "size_bytes": len(csv_bytes),
            }
        except S3Error as exc:
            logger.error("minio_upload_failed", key=key, error=str(exc))
            raise

    def list_snapshots(
        self,
        *,
        tenant_id: str,
        connection_id: str,
        table_name: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        List snapshots for a table, most recent first.
        Used by the drift detector to find the previous snapshot to compare against.
        """
        prefix = f"{tenant_id}/{connection_id}/{table_name}/"
        try:
            objects = list(self.client.list_objects(self.bucket, prefix=prefix))
            objects.sort(key=lambda o: o.last_modified, reverse=True)
            return [
                {
                    "object_key": o.object_name,
                    "size_bytes": o.size,
                    "last_modified": o.last_modified.isoformat(),
                }
                for o in objects[:limit]
            ]
        except S3Error as exc:
            logger.error("minio_list_failed", prefix=prefix, error=str(exc))
            return []

    def download_csv(self, object_key: str) -> bytes:
        """Download a CSV snapshot by its object key."""
        try:
            response = self.client.get_object(self.bucket, object_key)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as exc:
            logger.error("minio_download_failed", key=object_key, error=str(exc))
            raise

    def get_latest_two(
        self,
        *,
        tenant_id: str,
        connection_id: str,
        table_name: str,
    ) -> tuple[Optional[Dict], Optional[Dict]]:
        """
        Returns (latest, previous) snapshot metadata, or (latest, None) if
        only one snapshot exists, or (None, None) if no snapshots exist.
        Used directly by the drift detector.
        """
        snapshots = self.list_snapshots(
            tenant_id=tenant_id,
            connection_id=connection_id,
            table_name=table_name,
            limit=2,
        )
        latest = snapshots[0] if len(snapshots) > 0 else None
        previous = snapshots[1] if len(snapshots) > 1 else None
        return latest, previous


minio_storage = MinIOStorage()