"""Model picker API: list providers and models, save or reset the choice."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from agentic_chatbot.api.security import require_api_key
from agentic_chatbot.components.llm_loader import build_llm, describe_llm, reset_llm_cache
from agentic_chatbot.exception.exception import LLMConfigError
from agentic_chatbot.services.model_catalog import catalog
from agentic_chatbot.services.model_selection import clear_selection, save_selection

router = APIRouter(prefix="/api", tags=["models"], dependencies=[Depends(require_api_key)])

Provider = Literal["openrouter", "ollama", "claude", "openai", "local", "demo"]


class ModelChoice(BaseModel):
    provider: Provider
    model: str = Field(..., min_length=1, max_length=200)


class ModelSelectionIn(BaseModel):
    main: ModelChoice
    router: ModelChoice | None = Field(None, description="Leave out to route with the main model")


def _current() -> dict:
    llm = describe_llm()
    return {
        "main": llm["main"],
        "router": llm["router"],
        "source": llm["source"],
        "ready": llm["configured"],
        "error": llm["error"],
    }


@router.get("/models")
async def list_models(refresh: bool = False):
    """Providers with their models (fetched from each provider, cached 5 minutes) and the current choice."""
    return {"current": _current(), "providers": await catalog(refresh)}


@router.put("/models")
async def choose_models(body: ModelSelectionIn):
    """Save the model choice. It overrides LLM_PROVIDER in .env until reset."""
    choices = [("main", body.main), *([("router", body.router)] if body.router else [])]
    for role, choice in choices:
        try:
            build_llm(choice.provider, choice.model.strip(), role)  # catches a missing key before saving
        except LLMConfigError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.public_message) from exc
    save_selection(
        {"provider": body.main.provider, "model": body.main.model.strip()},
        {"provider": body.router.provider, "model": body.router.model.strip()} if body.router else None,
    )
    reset_llm_cache()
    return _current()


@router.delete("/models")
async def reset_models():
    """Forget the UI choice and go back to LLM_PROVIDER and the models in .env / config.yaml."""
    clear_selection()
    reset_llm_cache()
    return _current()
