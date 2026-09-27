"""
Unit tests for Unified Object Storage Service.

Tests signed upload URL generation for Supabase and S3 backends,
path formatting, and safe error handling.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.storage import StorageService


@pytest.mark.asyncio
async def test_generate_upload_url_local_mock_fallback() -> None:
    """When external credentials are absent, generates a valid structured mock upload URL."""
    storage = StorageService()
    res = await storage.generate_upload_url(
        tenant_id="tenant-123",
        document_id="doc-456",
        filename="report.pdf",
        expires_in=600,
    )

    assert "storage_path" in res
    assert "upload_url" in res
    assert res["storage_path"] == "tenant-123/doc-456/report.pdf"
    assert res["expires_in"] == 600
    assert res["method"] == "PUT"


@pytest.mark.asyncio
async def test_supabase_signed_url_generation() -> None:
    """When Supabase credentials are present, queries Supabase REST API."""
    with (
        patch("app.config.settings.supabase_url", "https://xyz.supabase.co"),
        patch("app.config.settings.supabase_service_role_key", "secret-key"),
    ):
        storage = StorageService()
        storage.supabase_url = "https://xyz.supabase.co"
        storage.service_key = "secret-key"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "url": (
                "/storage/v1/object/upload/sign/documents/"
                "tenant-123/doc-1/file.pdf?token=mock_upload_token"
            ),
            "token": "mock_upload_token",
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            res = await storage.generate_upload_url("tenant-123", "doc-1", "file.pdf")
            assert res["storage_backend"] == "supabase"
            assert "https://xyz.supabase.co/storage/v1/object/upload/sign" in res["upload_url"]
            assert res["token"] == "mock_upload_token"


@pytest.mark.asyncio
async def test_delete_file_handles_empty_path() -> None:
    """Deleting an empty storage path must return True safely without exceptions."""
    storage = StorageService()
    assert await storage.delete_file("") is True
