"""Model listing endpoint: GET /v1/models.

Exposes which public model identifiers the gateway supports, so clients (and our
own frontend dropdown in Step 15) can discover them without hardcoding a list.

We expose the public id and provider, but NOT internal details beyond that. The
data comes straight from the registry — the single source of truth.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.schemas.common import Provider
from app.services.model_registry import list_models

router = APIRouter(prefix="/v1/models", tags=["models"])


class ModelInfo(BaseModel):
    """Public description of one available model."""

    id: str            # the public identifier clients send, e.g. "gemini"
    provider: Provider  # which backend serves it


class ModelListResponse(BaseModel):
    """Response wrapper: a list of available models."""

    models: list[ModelInfo]


@router.get("", response_model=ModelListResponse)
async def get_models() -> ModelListResponse:
    """Return every model the gateway can serve."""
    return ModelListResponse(
        models=[
            ModelInfo(id=cfg.public_id, provider=cfg.provider)
            for cfg in list_models()
        ]
    )
