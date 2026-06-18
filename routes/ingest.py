"""
Document Ingestion Router
Handles file/folder upload → vector store ingestion for RAG
Includes comprehensive error handling and structured logging.
"""

import os
import shutil
import traceback
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from pydantic import BaseModel

import sys

# Ensure src is on the path
project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from agentic_chatbot.utils.document_loader import DocumentLoader
from agentic_chatbot.components.vector_store_loader import VectorStoreLoader
from agentic_chatbot.exception.exception import FileProcessingException, VectorStoreException
from agentic_chatbot.logging.logging_utils import (
    ExecutionTimer,
    get_correlation_id
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

# Upload directory for temporary file storage
UPLOAD_DIR = Path("workspace/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Track ingested documents (persisted as a simple JSON file)
INGEST_TRACKER_FILE = Path("workspace/ingested_docs.json")

# ── Pydantic Models ──────────────────────────────────────────────────────────

class IngestResponse(BaseModel):
    status: str
    message: str
    files_processed: int
    total_chunks: int
    documents: List[str]
    errors: List[str]

class IngestStatus(BaseModel):
    total_documents: int
    document_names: List[str]
    last_ingested: Optional[str] = None

class DocumentInfo(BaseModel):
    name: str
    chunks: int
    ingested_at: str
    file_type: str

# ── In-memory tracker (loaded from disk) ─────────────────────────────────────

import json

import json

def _load_tracker(correlation_id: str) -> dict:
    """Load the ingestion tracker from disk."""
    try:
        if INGEST_TRACKER_FILE.exists():
            with open(INGEST_TRACKER_FILE, "r") as f:
                tracker = json.load(f)
                logger.debug(
                    f"Loaded tracker with {len(tracker.get('documents', []))} documents",
                    extra={"correlation_id": correlation_id}
                )
                return tracker
    except Exception as e:
        logger.warning(
            f"Failed to load tracker: {str(e)}",
            extra={"correlation_id": correlation_id}
        )
    return {"documents": []}


def _save_tracker(data: dict, correlation_id: str):
    """Persist the ingestion tracker to disk."""
    try:
        INGEST_TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(INGEST_TRACKER_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.debug(
            f"Tracker saved with {len(data.get('documents', []))} documents",
            extra={"correlation_id": correlation_id}
        )
    except Exception as e:
        logger.error(
            f"Failed to save tracker: {str(e)}",
            extra={"correlation_id": correlation_id},
            exc_info=True
        )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=IngestResponse)
async def upload_and_ingest(files: List[UploadFile] = File(...), req: Request = None):
    """
    Upload files and ingest them into the vector store for RAG.
    Accepts multiple files via multipart/form-data.
    """
    correlation_id = req.headers.get("X-Correlation-ID") if req else get_correlation_id()

    with ExecutionTimer("upload_and_ingest", correlation_id, logger):
        try:
            if not files:
                logger.warning(
                    "Upload attempted with no files",
                    extra={"correlation_id": correlation_id}
                )
                raise HTTPException(status_code=400, detail="No files provided")

            logger.info(
                f"Starting document ingestion for {len(files)} file(s)",
                extra={"correlation_id": correlation_id}
            )

            document_loader = DocumentLoader()
            errors: List[str] = []
            processed_files: List[str] = []
            total_chunks = 0

            # Load the vector store once
            try:
                logger.debug(
                    "Loading vector store",
                    extra={"correlation_id": correlation_id}
                )
                vector_db = VectorStoreLoader().load_vectorstore()
            except Exception as e:
                logger.error(
                    f"Failed to load vector store: {str(e)}",
                    extra={"correlation_id": correlation_id},
                    exc_info=True
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to connect to vector store: {str(e)}"
                )

            tracker = _load_tracker(correlation_id)

            for upload_file in files:
                file_name = upload_file.filename or "unknown"
                save_path = UPLOAD_DIR / file_name

                try:
                    # Ensure subdirectories exist (for folder uploads with paths)
                    save_path.parent.mkdir(parents=True, exist_ok=True)

                    # Save file to disk
                    logger.debug(
                        f"Saving uploaded file: {file_name}",
                        extra={"correlation_id": correlation_id}
                    )

                    with open(save_path, "wb") as f:
                        content = await upload_file.read()
                        f.write(content)

                    print(f"📄 Processing: {file_name}")

                    # Load and chunk the document
                    logger.debug(
                        f"Loading and chunking document: {file_name}",
                        extra={"correlation_id": correlation_id}
                    )

                    docs = document_loader.load_documents(str(save_path))

                    if docs:
                        # Add to vector store
                        logger.debug(
                            f"Adding {len(docs)} chunks to vector store",
                            extra={"correlation_id": correlation_id}
                        )

                        vector_db.add_documents(docs)
                        chunk_count = len(docs)
                        total_chunks += chunk_count
                        processed_files.append(file_name)

                        # Track the document
                        tracker["documents"].append({
                            "name": file_name,
                            "chunks": chunk_count,
                            "ingested_at": datetime.now().isoformat(),
                            "file_type": Path(file_name).suffix.lower(),
                        })

                        logger.info(
                            f"Successfully ingested {file_name} ({chunk_count} chunks)",
                            extra={"correlation_id": correlation_id}
                        )

                        print(f"  ✅ Added {chunk_count} chunks from {file_name}")
                    else:
                        error_msg = f"{file_name}: No content extracted"
                        errors.append(error_msg)
                        logger.warning(
                            error_msg,
                            extra={"correlation_id": correlation_id}
                        )

                except Exception as e:
                    error_msg = f"{file_name}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(
                        f"Error processing {file_name}: {str(e)}",
                        extra={"correlation_id": correlation_id},
                        exc_info=True
                    )
                    print(f"  ❌ Error processing {file_name}: {e}")

                finally:
                    # Clean up temp file
                    try:
                        if save_path.exists():
                            save_path.unlink()
                    except Exception:
                        pass

            # Save the tracker
            _save_tracker(tracker, correlation_id)

            status = "success" if processed_files else "error"
            if processed_files and errors:
                status = "partial"

            logger.info(
                f"Ingestion completed: {len(processed_files)} file(s), {total_chunks} chunks",
                extra={
                    "correlation_id": correlation_id,
                    "status": status,
                    "files_processed": len(processed_files),
                    "errors": len(errors)
                }
            )

            return IngestResponse(
                status=status,
                message=f"Processed {len(processed_files)} file(s), {total_chunks} chunks added to knowledge base",
                files_processed=len(processed_files),
                total_chunks=total_chunks,
                documents=processed_files,
                errors=errors,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"Document ingestion failed: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Document ingestion failed: {str(e)}"
            )


@router.get("/status", response_model=IngestStatus)
async def get_ingest_status(req: Request = None):
    """Get current ingestion status and document count."""
    correlation_id = req.headers.get("X-Correlation-ID") if req else get_correlation_id()

    with ExecutionTimer("get_ingest_status", correlation_id, logger):
        try:
            tracker = _load_tracker(correlation_id)
            docs = tracker.get("documents", [])

            logger.info(
                f"Retrieved ingest status: {len(docs)} documents",
                extra={"correlation_id": correlation_id}
            )

            return IngestStatus(
                total_documents=len(docs),
                document_names=[d["name"] for d in docs],
                last_ingested=docs[-1]["ingested_at"] if docs else None,
            )
        except Exception as e:
            logger.error(
                f"Failed to get ingest status: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get ingest status: {str(e)}"
            )


@router.get("/documents", response_model=List[DocumentInfo])
async def list_ingested_documents(req: Request = None):
    """List all ingested documents with their details."""
    correlation_id = req.headers.get("X-Correlation-ID") if req else get_correlation_id()

    with ExecutionTimer("list_ingested_documents", correlation_id, logger):
        try:
            tracker = _load_tracker(correlation_id)
            docs = tracker.get("documents", [])

            logger.info(
                f"Listed {len(docs)} ingested documents",
                extra={"correlation_id": correlation_id}
            )

            return [
                DocumentInfo(
                    name=d["name"],
                    chunks=d["chunks"],
                    ingested_at=d["ingested_at"],
                    file_type=d.get("file_type", "unknown"),
                )
                for d in docs
            ]
        except Exception as e:
            logger.error(
                f"Failed to list ingested documents: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list documents: {str(e)}"
            )


@router.delete("/documents")
async def clear_knowledge_base(req: Request = None):
    """Clear all documents from the knowledge base tracker.

    NOTE: This clears the tracker only.  Full PGVector collection
    clearing would require dropping and recreating the collection.
    """
    correlation_id = req.headers.get("X-Correlation-ID") if req else get_correlation_id()

    with ExecutionTimer("clear_knowledge_base", correlation_id, logger):
        try:
            logger.warning(
                "Clearing knowledge base tracker",
                extra={"correlation_id": correlation_id}
            )

            _save_tracker({"documents": []}, correlation_id)

            logger.info(
                "Knowledge base tracker cleared successfully",
                extra={"correlation_id": correlation_id}
            )

            return {
                "success": True,
                "message": "Knowledge base tracker cleared",
            }
        except Exception as e:
            logger.error(
                f"Error clearing knowledge base: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Error clearing knowledge base: {str(e)}",
            )
