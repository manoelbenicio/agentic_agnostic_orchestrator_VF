from __future__ import annotations

from decimal import Decimal
from threading import RLock
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator


ProviderName = Annotated[str, Field(min_length=1)]
ModelId = Annotated[str, Field(min_length=1)]


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: ModelId
    provider: ProviderName
    model_name: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    context_window: int = Field(gt=0)
    cost_per_1k_input: Decimal = Field(ge=Decimal("0"))
    cost_per_1k_output: Decimal = Field(ge=Decimal("0"))
    is_active: bool = True
    capabilities: list[str] = Field(default_factory=list)

    @field_validator("model_id", "provider", "model_name", "display_name")
    @classmethod
    def normalize_required_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @field_validator("capabilities")
    @classmethod
    def normalize_capabilities(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for capability in value:
            item = capability.strip().lower()
            if not item:
                raise ValueError("capabilities entries must not be blank")
            if item not in seen:
                normalized.append(item)
                seen.add(item)
        return normalized


class ModelConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderName | None = None
    model_name: str | None = Field(default=None, min_length=1)
    display_name: str | None = Field(default=None, min_length=1)
    context_window: int | None = Field(default=None, gt=0)
    cost_per_1k_input: Decimal | None = Field(default=None, ge=Decimal("0"))
    cost_per_1k_output: Decimal | None = Field(default=None, ge=Decimal("0"))
    is_active: bool | None = None
    capabilities: list[str] | None = None

    @field_validator("provider", "model_name", "display_name")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @field_validator("capabilities")
    @classmethod
    def normalize_optional_capabilities(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        return ModelConfig.normalize_capabilities(value)


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, ModelConfig] = {}
        self._lock = RLock()

    def register_model(self, model: ModelConfig) -> ModelConfig:
        with self._lock:
            if model.model_id in self._models:
                raise ValueError(f"model {model.model_id!r} already exists")
            stored = model.model_copy(deep=True)
            self._models[stored.model_id] = stored
            return stored.model_copy(deep=True)

    def get_model(self, model_id: str) -> ModelConfig | None:
        with self._lock:
            model = self._models.get(model_id)
            return model.model_copy(deep=True) if model is not None else None

    def list_models(self, *, include_inactive: bool = False) -> list[ModelConfig]:
        with self._lock:
            models = list(self._models.values())
        if not include_inactive:
            models = [model for model in models if model.is_active]
        return [model.model_copy(deep=True) for model in sorted(models, key=lambda item: item.model_id)]

    def update_model(self, model_id: str, updates: ModelConfigUpdate | dict[str, object]) -> ModelConfig:
        update_model = updates if isinstance(updates, ModelConfigUpdate) else ModelConfigUpdate.model_validate(updates)
        patch = update_model.model_dump(exclude_unset=True)
        with self._lock:
            existing = self._models.get(model_id)
            if existing is None:
                raise KeyError(model_id)
            updated = existing.model_copy(update=patch, deep=True)
            self._models[model_id] = updated
            return updated.model_copy(deep=True)

    def deactivate_model(self, model_id: str) -> ModelConfig:
        return self.update_model(model_id, ModelConfigUpdate(is_active=False))

    def get_models_by_provider(self, provider: str, *, include_inactive: bool = False) -> list[ModelConfig]:
        normalized = provider.strip().lower()
        with self._lock:
            models = [
                model
                for model in self._models.values()
                if model.provider.strip().lower() == normalized and (include_inactive or model.is_active)
            ]
        return [model.model_copy(deep=True) for model in sorted(models, key=lambda item: item.model_id)]

    def clear(self) -> None:
        with self._lock:
            self._models.clear()


model_registry = ModelRegistry()
router = APIRouter(prefix="/v1/models", tags=["Model Registry"])


@router.post("", response_model=ModelConfig, status_code=status.HTTP_201_CREATED)
async def register_model(model: ModelConfig) -> ModelConfig:
    try:
        return model_registry.register_model(model)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("", response_model=list[ModelConfig])
async def list_models(
    provider: str | None = Query(default=None, min_length=1),
    include_inactive: bool = False,
) -> list[ModelConfig]:
    if provider:
        return model_registry.get_models_by_provider(provider, include_inactive=include_inactive)
    return model_registry.list_models(include_inactive=include_inactive)


@router.get("/providers/{provider}", response_model=list[ModelConfig])
async def get_models_by_provider(provider: str, include_inactive: bool = False) -> list[ModelConfig]:
    return model_registry.get_models_by_provider(provider, include_inactive=include_inactive)


@router.get("/{model_id}", response_model=ModelConfig)
async def get_model(model_id: str) -> ModelConfig:
    model = model_registry.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model not found")
    return model


@router.put("/{model_id}", response_model=ModelConfig)
async def update_model(model_id: str, updates: ModelConfigUpdate) -> ModelConfig:
    try:
        return model_registry.update_model(model_id, updates)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model not found") from exc


@router.delete("/{model_id}", response_model=ModelConfig)
async def deactivate_model(model_id: str) -> ModelConfig:
    try:
        return model_registry.deactivate_model(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model not found") from exc
