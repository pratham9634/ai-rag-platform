"""
Enterprise Integration Tests for Pre-Signed Direct Uploads & Celery Ingestion.

Tests:
1. Direct storage upload-url endpoint generates valid signed URLs.
2. Quota & size enforcement on upload-url requests.
3. Confirm upload triggers Celery worker dispatch.
4. Celery application queue configuration (durable ingestion + dead-letter queue).
"""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.security import AuthenticatedUser, get_current_tenant_id, get_current_user
from app.database.models import Document
from app.database.session import get_db
from app.main import app
from app.workers.celery_app import celery_app


@pytest.fixture
def mock_db() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def test_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id="user_admin",
        tenant_id="tenant-enterprise",
        org_id="tenant-enterprise",
        org_role="admin",
        is_authenticated=True,
    )


def test_generate_upload_url_success(mock_db: AsyncMock, test_user: AuthenticatedUser) -> None:
    """POST /api/documents/upload-url should return signed URL and create PENDING record."""

    async def override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_current_tenant_id] = lambda: "tenant-enterprise"

    # Mock quota queries
    count_mock = MagicMock()
    count_mock.scalar.return_value = 2  # 2 existing docs
    mock_db.execute.return_value = count_mock

    client = TestClient(app)
    headers = {"Authorization": "Bearer mock-token-for-dev", "x-tenant-id": "tenant-enterprise"}

    resp = client.post(
        "/api/documents/upload-url",
        json={"filename": "architecture.pdf", "file_size": 1024 * 1024},
        headers=headers,
    )

    app.dependency_overrides.clear()

    assert resp.status_code == 201
    data = resp.json()
    assert "upload_url" in data
    assert "document_id" in data
    assert "tenant-enterprise" in data["storage_path"]
    assert data["method"] == "PUT"


def test_generate_upload_url_rejects_oversized_file(
    mock_db: AsyncMock, test_user: AuthenticatedUser
) -> None:
    """POST /api/documents/upload-url should return 413 when file exceeds 10MB."""

    async def override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_current_tenant_id] = lambda: "tenant-enterprise"

    client = TestClient(app)
    headers = {"Authorization": "Bearer mock-token-for-dev", "x-tenant-id": "tenant-enterprise"}

    resp = client.post(
        "/api/documents/upload-url",
        json={"filename": "huge_file.pdf", "file_size": 25 * 1024 * 1024},  # 25 MB
        headers=headers,
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 413
    assert "exceeds maximum allowed limit" in resp.json()["detail"]


def test_confirm_upload_triggers_celery_task(
    mock_db: AsyncMock, test_user: AuthenticatedUser
) -> None:
    """POST /api/documents/confirm-upload should locate document and dispatch task."""
    doc_id = uuid.uuid4()
    mock_doc = Document(
        id=doc_id,
        tenant_id="tenant-enterprise",
        filename="specs.pdf",
        file_size=5000,
        storage_path="tenant-enterprise/doc/specs.pdf",
        status="PENDING",
    )

    query_mock = MagicMock()
    query_mock.scalar_one_or_none.return_value = mock_doc
    mock_db.execute.return_value = query_mock

    async def override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_current_tenant_id] = lambda: "tenant-enterprise"

    client = TestClient(app)
    headers = {"Authorization": "Bearer mock-token-for-dev", "x-tenant-id": "tenant-enterprise"}

    with patch("app.workers.ingestion_tasks.ingest_document_task.delay") as mock_delay:
        resp = client.post(
            "/api/documents/confirm-upload",
            json={"document_id": str(doc_id)},
            headers=headers,
        )

        assert resp.status_code == 202
        assert resp.json()["status"] == "PENDING"
        mock_delay.assert_called_once_with(
            document_id=str(doc_id),
            tenant_id="tenant-enterprise",
            storage_path="tenant-enterprise/doc/specs.pdf",
            filename="specs.pdf",
        )

    app.dependency_overrides.clear()


def test_celery_queues_configured_with_dlq() -> None:
    """Celery application configuration must declare documents.ingestion and documents.dlq."""
    queue_names = [q.name for q in celery_app.conf.task_queues]
    assert "documents.ingestion" in queue_names
    assert "documents.dlq" in queue_names

    # Check dead-letter routing argument on main queue
    ingestion_q = next(q for q in celery_app.conf.task_queues if q.name == "documents.ingestion")
    assert ingestion_q.queue_arguments.get("x-dead-letter-exchange") == "documents.dlx"
    assert ingestion_q.queue_arguments.get("x-dead-letter-routing-key") == "documents.dlq"
