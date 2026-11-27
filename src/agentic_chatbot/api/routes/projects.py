"""Projects: workspaces with their own chats, documents and instructions.

    GET    /api/projects               every project, with chat and document counts
    POST   /api/projects               create one ({name, instructions})
    GET    /api/projects/{id}          one project
    PATCH  /api/projects/{id}          rename or change its instructions
    DELETE /api/projects/{id}?confirm=true   delete it with its chats and documents

A project's chats search only its documents and follow its instructions (see
core/scope.py). Chats and files outside projects never see a project's files.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from agentic_chatbot.api.routes.history import _forget_thread
from agentic_chatbot.api.schemas import ProjectIn, ProjectOut, ProjectPatch
from agentic_chatbot.api.security import require_api_key
from agentic_chatbot.services.knowledge_base import get_knowledge_base
from agentic_chatbot.services.store import get_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/projects", tags=["projects"], dependencies=[Depends(require_api_key)])


async def _project_or_404(project_id: str) -> dict:
    project = await get_store().get_project(project_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")
    return project


@router.get("", response_model=list[ProjectOut])
async def list_projects():
    return await get_store().list_projects()


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectIn):
    return await get_store().create_project(f"p_{uuid.uuid4().hex[:16]}", body.name, body.instructions.strip())


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str):
    return await _project_or_404(project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: str, body: ProjectPatch):
    await _project_or_404(project_id)
    name = " ".join(body.name.split()) if body.name is not None else None
    if name == "":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give the project a name.")
    instructions = body.instructions.strip() if body.instructions is not None else None
    return await get_store().update_project(project_id, name, instructions)


@router.delete("/{project_id}")
async def delete_project(project_id: str, request: Request, confirm: bool = Query(False)):
    """Deletes the project, its chats (and their memory of the thread) and its documents (and their vectors)."""
    project = await _project_or_404(project_id)
    if not confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Deleting {project['name']} removes its chats and documents. Pass ?confirm=true.")
    store = get_store()
    chats = await store.list_conversations(limit=10_000, project=project_id)
    for c in chats:
        await store.delete_conversation(c["id"])
        await _forget_thread(request, c["id"])
    kb = get_knowledge_base()
    docs = [d for d in await store.list_documents() if d.get("project_id") == project_id]
    for d in docs:
        await kb.delete_document(d["id"])
    await store.delete_project(project_id)
    logger.info("Deleted project %s with %d chats and %d documents", project_id, len(chats), len(docs))
    return {"deleted": project_id, "chats": len(chats), "documents": len(docs)}
