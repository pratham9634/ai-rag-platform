"""
Health endpoint tests.

These tests verify that the /health endpoint works correctly.
This is our first test — every subsequent feature will also have tests.

Why test /health?
- Verifies the FastAPI app starts correctly
- Verifies routing works
- Serves as the foundation for all future API tests
- CI/CD pipeline will run this on every PR
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200() -> None:
    """Health endpoint should return 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_healthy_status() -> None:
    """Health endpoint should report healthy status."""
    response = client.get("/health")
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "enterprise-rag-api"


def test_health_returns_version() -> None:
    """Health endpoint should include a version string."""
    response = client.get("/health")
    data = response.json()
    assert "version" in data
    assert isinstance(data["version"], str)
