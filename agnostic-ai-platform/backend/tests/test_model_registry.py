from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.main import create_app
from app.model_registry import ModelConfig, ModelConfigUpdate, ModelRegistry, model_registry


def auth_headers() -> dict[str, str]:
    token = create_access_token(user_id="user-1", role="admin", tenant_id="tenant-1")
    return {"Authorization": f"Bearer {token}"}


def sample_model(model_id: str = "openai:gpt-4o-mini", provider: str = "openai") -> dict[str, object]:
    return {
        "model_id": model_id,
        "provider": provider,
        "model_name": "gpt-4o-mini",
        "display_name": "GPT-4o mini",
        "context_window": 128000,
        "cost_per_1k_input": "0.00015",
        "cost_per_1k_output": "0.00060",
        "is_active": True,
        "capabilities": ["chat", "tools", "CHAT"],
    }


def test_model_registry_register_get_list_update_deactivate_and_provider_filter() -> None:
    registry = ModelRegistry()
    created = registry.register_model(ModelConfig.model_validate(sample_model()))

    assert created.model_id == "openai:gpt-4o-mini"
    assert created.capabilities == ["chat", "tools"]
    assert registry.get_model(created.model_id) == created
    assert registry.list_models() == [created]
    assert registry.get_models_by_provider("OPENAI") == [created]

    updated = registry.update_model(
        created.model_id,
        ModelConfigUpdate(display_name="GPT-4o Mini Updated", cost_per_1k_input=Decimal("0.00010")),
    )

    assert updated.display_name == "GPT-4o Mini Updated"
    assert updated.cost_per_1k_input == Decimal("0.00010")

    inactive = registry.deactivate_model(created.model_id)
    assert inactive.is_active is False
    assert registry.list_models() == []
    assert registry.list_models(include_inactive=True) == [inactive]


def test_model_registry_rejects_duplicate_model_id() -> None:
    registry = ModelRegistry()
    model = ModelConfig.model_validate(sample_model())

    registry.register_model(model)

    try:
        registry.register_model(model)
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("duplicate model registration should fail")


def test_model_registry_crud_endpoints() -> None:
    model_registry.clear()
    client = TestClient(create_app())

    created = client.post("/v1/models", headers=auth_headers(), json=sample_model())

    assert created.status_code == 201
    assert created.json()["capabilities"] == ["chat", "tools"]

    duplicate = client.post("/v1/models", headers=auth_headers(), json=sample_model())
    assert duplicate.status_code == 409

    listed = client.get("/v1/models", headers=auth_headers())
    assert listed.status_code == 200
    assert [item["model_id"] for item in listed.json()] == ["openai:gpt-4o-mini"]

    provider_models = client.get("/v1/models/providers/openai", headers=auth_headers())
    assert provider_models.status_code == 200
    assert provider_models.json()[0]["provider"] == "openai"

    fetched = client.get("/v1/models/openai:gpt-4o-mini", headers=auth_headers())
    assert fetched.status_code == 200
    assert fetched.json()["display_name"] == "GPT-4o mini"

    updated = client.put(
        "/v1/models/openai:gpt-4o-mini",
        headers=auth_headers(),
        json={"display_name": "GPT-4o Mini Updated", "is_active": True},
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "GPT-4o Mini Updated"

    deactivated = client.delete("/v1/models/openai:gpt-4o-mini", headers=auth_headers())
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    active_only = client.get("/v1/models", headers=auth_headers())
    assert active_only.json() == []

    include_inactive = client.get("/v1/models?include_inactive=true", headers=auth_headers())
    assert include_inactive.json()[0]["model_id"] == "openai:gpt-4o-mini"


def test_model_registry_endpoint_returns_404_for_missing_model() -> None:
    model_registry.clear()
    client = TestClient(create_app())

    response = client.get("/v1/models/missing", headers=auth_headers())

    assert response.status_code == 404
    assert response.json()["detail"] == "model not found"
