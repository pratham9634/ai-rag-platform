"""
Unified Object Storage Service (Supabase Storage & AWS S3).

Provides signed direct upload URLs to bypass API server RAM during uploads,
secure authenticated downloads, and file deletion lifecycle management.
"""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Enterprise multi-backend object storage client."""

    def __init__(self) -> None:
        self.backend = (settings.storage_backend or "supabase").lower()
        self.bucket = settings.supabase_storage_bucket or "documents"
        self.supabase_url = settings.supabase_url.rstrip("/") if settings.supabase_url else ""
        self.service_key = settings.supabase_service_role_key

    async def generate_upload_url(
        self,
        tenant_id: str,
        document_id: str,
        filename: str,
        expires_in: int = 900,
    ) -> dict[str, Any]:
        """
        Generate a pre-signed direct upload URL for client-to-storage upload.

        Client uploads binary directly to object storage with HTTP PUT.
        """
        clean_filename = filename.replace("/", "_").replace("\\", "_")
        storage_path = f"{tenant_id}/{document_id}/{clean_filename}"

        if self.backend == "s3" and settings.aws_access_key_id:
            try:
                import boto3
                from botocore.config import Config

                s3_config = Config(signature_version="s3v4")
                kwargs: dict[str, Any] = {
                    "region_name": settings.aws_region,
                    "aws_access_key_id": settings.aws_access_key_id,
                    "aws_secret_access_key": settings.aws_secret_access_key,
                    "config": s3_config,
                }
                if settings.s3_endpoint_url:
                    kwargs["endpoint_url"] = settings.s3_endpoint_url

                s3 = boto3.client("s3", **kwargs)
                url = s3.generate_presigned_url(
                    ClientMethod="put_object",
                    Params={
                        "Bucket": settings.s3_bucket_name or self.bucket,
                        "Key": storage_path,
                    },
                    ExpiresIn=expires_in,
                )
                return {
                    "storage_backend": "s3",
                    "storage_path": storage_path,
                    "upload_url": url,
                    "expires_in": expires_in,
                    "method": "PUT",
                }
            except Exception as e:
                logger.warning(
                    "Failed to generate S3 presigned URL: %s. Using Supabase fallback.", e
                )

        # Default Supabase Storage REST API
        if self.supabase_url and self.service_key:
            endpoint = (
                f"{self.supabase_url}/storage/v1/object/upload/sign/{self.bucket}/{storage_path}"
            )
            headers = {
                "Authorization": f"Bearer {self.service_key}",
                "apikey": self.service_key,
                "Content-Type": "application/json",
            }
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        endpoint, json={"expiresIn": expires_in}, headers=headers
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        relative_url = data.get("url", "")
                        # Supabase returns relative url e.g. /storage/v1/object/upload/sign/...
                        full_upload_url = f"{self.supabase_url}{relative_url}"
                        return {
                            "storage_backend": "supabase",
                            "storage_path": storage_path,
                            "upload_url": full_upload_url,
                            "token": data.get("token"),
                            "expires_in": expires_in,
                            "method": "PUT",
                        }
                    logger.warning(
                        "Supabase storage signing failed: %d - %s", resp.status_code, resp.text
                    )
            except Exception as e:
                logger.warning("Supabase signed URL generation encountered error: %s", e)

        # Fallback local direct path simulation for tests/offline
        mock_url = f"https://storage.local/upload/{self.bucket}/{storage_path}"
        return {
            "storage_backend": "local_mock",
            "storage_path": storage_path,
            "upload_url": mock_url,
            "expires_in": expires_in,
            "method": "PUT",
        }

    async def upload_file_bytes(
        self,
        storage_path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> bool:
        """Upload raw file bytes directly to object storage."""
        if self.backend == "s3" and settings.aws_access_key_id:
            try:
                import boto3

                kwargs: dict[str, Any] = {
                    "region_name": settings.aws_region,
                    "aws_access_key_id": settings.aws_access_key_id,
                    "aws_secret_access_key": settings.aws_secret_access_key,
                }
                if settings.s3_endpoint_url:
                    kwargs["endpoint_url"] = settings.s3_endpoint_url
                s3 = boto3.client("s3", **kwargs)
                s3.put_object(
                    Bucket=settings.s3_bucket_name or self.bucket,
                    Key=storage_path,
                    Body=content,
                    ContentType=content_type,
                )
                return True
            except Exception as e:
                logger.error("Failed to upload to S3: %s", e)
                raise

        # Supabase Storage binary upload
        if self.supabase_url and self.service_key:
            endpoint = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{storage_path}"
            headers = {
                "Authorization": f"Bearer {self.service_key}",
                "apikey": self.service_key,
                "Content-Type": content_type,
                "x-upsert": "true",
            }
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(endpoint, content=content, headers=headers)
                    if resp.status_code in {200, 201}:
                        logger.info(
                            "Uploaded %d bytes to Supabase storage at %s",
                            len(content),
                            storage_path,
                        )
                        return True
                    logger.error(
                        "Supabase upload returned HTTP %d: %s", resp.status_code, resp.text
                    )
                    raise RuntimeError(f"Supabase upload failed: {resp.status_code} {resp.text}")
            except Exception as e:
                logger.error("Failed to upload to Supabase storage: %s", e)
                raise

        logger.info("Using local mock storage for %s (%d bytes)", storage_path, len(content))
        return True

    async def download_file_bytes(self, storage_path: str) -> bytes:
        """Download raw file bytes from object storage."""
        if self.backend == "s3" and settings.aws_access_key_id:
            try:
                import boto3

                kwargs: dict[str, Any] = {
                    "region_name": settings.aws_region,
                    "aws_access_key_id": settings.aws_access_key_id,
                    "aws_secret_access_key": settings.aws_secret_access_key,
                }
                if settings.s3_endpoint_url:
                    kwargs["endpoint_url"] = settings.s3_endpoint_url
                s3 = boto3.client("s3", **kwargs)
                response = s3.get_object(
                    Bucket=settings.s3_bucket_name or self.bucket,
                    Key=storage_path,
                )
                return bytes(response["Body"].read())
            except Exception as e:
                logger.error("Failed to download from S3: %s", e)

        # Supabase Storage authenticated download
        if self.supabase_url and self.service_key:
            endpoint = (
                f"{self.supabase_url}/storage/v1/object/authenticated/{self.bucket}/{storage_path}"
            )
            headers = {
                "Authorization": f"Bearer {self.service_key}",
                "apikey": self.service_key,
            }
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(endpoint, headers=headers)
                    if resp.status_code == 200:
                        return resp.content
                    logger.error(
                        "Supabase download returned HTTP %d: %s", resp.status_code, resp.text
                    )
            except Exception as e:
                logger.error("Failed to download from Supabase storage: %s", e)

        raise FileNotFoundError(
            f"Storage path {storage_path} could not be retrieved from {self.backend}."
        )

    async def delete_file(self, storage_path: str) -> bool:
        """Delete file from object storage."""
        if not storage_path:
            return True

        if self.backend == "s3" and settings.aws_access_key_id:
            try:
                import boto3

                kwargs: dict[str, Any] = {
                    "region_name": settings.aws_region,
                    "aws_access_key_id": settings.aws_access_key_id,
                    "aws_secret_access_key": settings.aws_secret_access_key,
                }
                if settings.s3_endpoint_url:
                    kwargs["endpoint_url"] = settings.s3_endpoint_url
                s3 = boto3.client("s3", **kwargs)
                s3.delete_object(Bucket=settings.s3_bucket_name or self.bucket, Key=storage_path)
                return True
            except Exception as e:
                logger.warning("Failed to delete object from S3: %s", e)

        if self.supabase_url and self.service_key:
            endpoint = f"{self.supabase_url}/storage/v1/object/{self.bucket}"
            headers = {
                "Authorization": f"Bearer {self.service_key}",
                "apikey": self.service_key,
                "Content-Type": "application/json",
            }
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.request(
                        "DELETE", endpoint, json={"prefixes": [storage_path]}, headers=headers
                    )
                    return resp.status_code in {200, 204}
            except Exception as e:
                logger.warning("Failed to delete object from Supabase storage: %s", e)

        return True
