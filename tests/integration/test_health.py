"""Integration tests for health endpoints."""

import pytest
from httpx import AsyncClient

from conduit import __version__


@pytest.mark.integration
class TestHealth:
    async def test_liveness(self, client: AsyncClient) -> None:
        response = await client.get("/admin/v1/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == __version__

    async def test_readiness(self, client: AsyncClient) -> None:
        response = await client.get("/admin/v1/health/ready")
        # May be 200 or 503 depending on DB/Redis availability in test
        assert response.status_code in (200, 503)
        data = response.json()
        assert "database" in data
        assert "redis" in data


@pytest.mark.integration
class TestAuth:
    async def test_missing_auth_header(self, client: AsyncClient) -> None:
        response = await client.get("/v1/models")
        assert response.status_code == 401

    async def test_invalid_auth_header(self, client: AsyncClient) -> None:
        response = await client.get(
            "/v1/models",
            headers={"Authorization": "Bearer invalid_key"},
        )
        assert response.status_code == 401

    async def test_master_key_auth(self, client: AsyncClient, admin_headers: dict) -> None:
        response = await client.get("/v1/models", headers=admin_headers)
        assert response.status_code == 200


@pytest.mark.integration
class TestKeyManagement:
    async def test_create_and_list_keys(
        self, client: AsyncClient, admin_headers: dict
    ) -> None:
        # Create
        create_resp = await client.post(
            "/admin/v1/keys/",
            headers=admin_headers,
            json={
                "user_email": "dev@example.com",
                "alias": "test-key",
                "budget_limit_usd": 10.0,
            },
        )
        assert create_resp.status_code == 201
        data = create_resp.json()
        assert data["key"].startswith("cnd_sk_")
        assert data["alias"] == "test-key"

        # List
        list_resp = await client.get("/admin/v1/keys/", headers=admin_headers)
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert list_data["total"] >= 1

    async def test_revoke_key(
        self, client: AsyncClient, admin_headers: dict
    ) -> None:
        # Create key
        resp = await client.post(
            "/admin/v1/keys/",
            headers=admin_headers,
            json={"user_email": "revoke@example.com"},
        )
        key_id = resp.json()["id"]
        raw_key = resp.json()["key"]

        # Verify it works
        models_resp = await client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert models_resp.status_code == 200

        # Revoke
        revoke_resp = await client.delete(
            f"/admin/v1/keys/{key_id}", headers=admin_headers
        )
        assert revoke_resp.status_code == 204

        # Verify it no longer works
        models_resp2 = await client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert models_resp2.status_code == 401