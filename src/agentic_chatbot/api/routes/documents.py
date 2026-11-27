"""Knowledge base: upload, list and delete documents."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from agentic_chatbot.api.schemas import DocumentOut, UploadResponse, UploadResult
from agentic_chatbot.api.security import rate_limit, require_api_key
from agentic_chatbot.core.settings import get_settings
from agentic_chatbot.exception.exception import CustomException
from agentic_chatbot.services.knowledge_base import get_knowledge_base
from agentic_chatbot.services.store import NO_PROJECT, get_store
from agentic_chatbot.utils.document_loader import SUPPORTED_EXTENSIONS, safe_filename

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["documents"], dependencies=[Depends(require_api_key)])

MAX_FILES_PER_UPLOAD = 50


async def _save_upload(upload: UploadFile, dest: Path, max_bytes: int) -> int:
    size = 0
    with open(dest, "wb") as fh:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                total = upload.size or size
                raise ValueError(
                    f"larger than {max_bytes // (1024 * 1024)} MB ({total / (1024 * 1024):.1f} MB). "
                    "Raise MAX_UPLOAD_MB in .env to allow bigger files"
                )
            fh.write(chunk)
    return size


@router.post("/documents", response_model=UploadResponse, dependencies=[Depends(rate_limit)])
async def upload_documents(files: list[UploadFile] = File(...),
                           project_id: str | None = Form(None, max_length=64)) -> UploadResponse:
    """Upload files (PDF, text, Markdown, CSV, JSON, code) and index them for document Q&A.
    With ``project_id`` they belong to that project and only its chats can read them."""
    project_id = project_id or None
    if project_id and not await get_store().get_project(project_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")
    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No files were sent.")
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Send at most {MAX_FILES_PER_UPLOAD} files at a time.")

    settings = get_settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    kb = get_knowledge_base()
    results: list[UploadResult] = []
    chunks = 0

    for upload in files:
        name = safe_filename(upload.filename or "upload")
        ext = Path(name).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            results.append(UploadResult(name=name, status="error", error=f"{ext or 'This file type'} isn't supported."))
            continue
        tmp = settings.uploads_dir / f"{uuid.uuid4().hex}{ext}"
        try:
            size = await _save_upload(upload, tmp, max_bytes)
            record = await kb.ingest_file(tmp, name, size, project_id=project_id)
            chunks += record["chunks"]
            doc = await get_store().get_document(record["id"])
            results.append(UploadResult(name=name, status="ok", document=doc))
        except ValueError as exc:
            results.append(UploadResult(name=name, status="error", error=f"{name} is {exc}."))
        except CustomException as exc:
            logger.warning("Ingest failed for %s: %s", name, exc)
            results.append(UploadResult(name=name, status="error", error=exc.public_message))
        except Exception:
            logger.exception("Unexpected ingest failure for %s", name)
            results.append(UploadResult(name=name, status="error", error=f"Couldn't index {name}."))
        finally:
            await upload.close()
            tmp.unlink(missing_ok=True)

    added = sum(1 for r in results if r.status == "ok")
    return UploadResponse(results=results, documents_added=added, chunks_added=chunks)


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(project: str | None = Query(None, max_length=64,
                                                     description="A project id, or 'none' for the general library")):
    docs = await get_store().list_documents()
    if project is None:
        return docs
    want = None if project == NO_PROJECT else project
    return [d for d in docs if (d.get("project_id") or None) == want]


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(doc_id: str):
    if not await get_knowledge_base().delete_document(doc_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")


@router.delete("/documents")
async def clear_documents(confirm: bool = Query(False)):
    if not confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pass ?confirm=true to remove every document.")
    return {"deleted": await get_knowledge_base().clear()}
