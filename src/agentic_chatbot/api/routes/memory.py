"""Long-term memory: see, add and delete what the assistant remembers about the user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from agentic_chatbot.api.schemas import MemoryIn, MemoryList, MemoryOut
from agentic_chatbot.api.security import require_api_key
from agentic_chatbot.services.long_term_memory import (
    add_memory,
    clear_memories,
    default_user_id,
    delete_memory,
    get_memory_store,
    list_memories,
    long_term_enabled,
    memory_backend,
)

router = APIRouter(prefix="/api/memory", tags=["memory"], dependencies=[Depends(require_api_key)])


def _store():
    store = get_memory_store()
    if store is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Long-term memory is still starting. Try again shortly.")
    return store


@router.get("", response_model=MemoryList)
async def get_memories() -> MemoryList:
    """Everything remembered about the user, newest first."""
    store = get_memory_store()
    items = await list_memories(store, default_user_id()) if store is not None else []
    return MemoryList(enabled=long_term_enabled(), backend=memory_backend(), user_id=default_user_id(),
                      items=[MemoryOut(**m) for m in items])


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
async def create_memory(body: MemoryIn) -> MemoryOut:
    """Add a memory by hand ("Prefers metric units")."""
    saved = await add_memory(_store(), default_user_id(), body.content, source="manual")
    if not saved:
        raise HTTPException(422,
                            "That can't be saved. Memories can't hold passwords, keys or card numbers.")
    return MemoryOut(**saved)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_memory(memory_id: str) -> None:
    if not await delete_memory(_store(), default_user_id(), memory_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memory not found.")


@router.delete("")
async def forget_everything(confirm: bool = False) -> dict:
    """Delete every memory. Requires ``?confirm=true``."""
    if not confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add ?confirm=true to delete every memory.")
    return {"deleted": await clear_memories(_store(), default_user_id())}
