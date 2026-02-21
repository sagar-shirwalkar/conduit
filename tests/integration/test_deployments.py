"""Integration tests for deployment management."""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestDeploymentManagement:
    async def test_create_deployment(
        self, client: AsyncClient, admin_headers: dict
    ) -> None:
        resp = await client.post(
            "/admin/v1/models/deployments/",
            headers=admin_headers,
            json={
                "name": "test-gpt4o",
                "provider": "openai",
                "model_name": "gpt-4o",
                "api_base": "https://api.openai.com/v1",
                "api_key": "sk-test-key",
                "priority": 1,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-gpt4o"
        assert data["provider"] == "openai"
        assert data["model_name"] == "gpt-4o"
        assert data["is_active"] is True
        assert data["is_healthy"] is True

    async def test_list_deployments(
        self, client: AsyncClient, admin_headers: dict
    ) -> None:
        # Create first
        await client.post(
            "/admin/v1/models/deployments/",
            headers=admin_headers,
            json={
                "name": "list-test-deploy",
                "provider": "openai",
                "model_name": "gpt-4o-mini",
                "api_base": "https://api.openai.com/v1",
                "api_key": "sk-test",
            },
        )

        resp = await client.get(
            "/admin/v1/models/deployments/", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    async def test_delete_deployment(
        self, client: AsyncClient, admin_headers: dict
    ) -> None:
        # Create
        create_resp = await client.post(
            "/admin/v1/models/deployments/",
            headers=admin_headers,
            json={
                "name": "delete-me",
                "provider": "openai",
                "model_name": "gpt-3.5-turbo",
                "api_base": "https://api.openai.com/v1",
                "api_key": "sk-test",
            },
        )
        dep_id = create_resp.json()["id"]

        # Delete
        del_resp = await client.delete(
            f"/admin/v1/models/deployments/{dep_id}", headers=admin_headers
        )
        assert del_resp.status_code == 204