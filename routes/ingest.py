"""
Document Ingestion Router
Handles file/folder upload → vector store ingestion for RAG
"""

import os
import shutil
import traceback
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

import sys

# Ensure src is on the path
project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from agentic_chatbot.utils.document_loader import DocumentLoader
from agentic_chatbot.components.vector_store_loader import VectorStoreLoader

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

def _load_tracker() -> dict:
    """Load the ingestion tracker from disk."""
    if INGEST_TRACKER_FILE.exists():
        try:
            with open(INGEST_TRACKER_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {"documents": []}
    return {"documents": []}

def _save_tracker(data: dict):
    """Persist the ingestion tracker to disk."""
    INGEST_TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(INGEST_TRACKER_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=IngestResponse)
async def upload_and_ingest(files: List[UploadFile] = File(...)):
    """
    Upload files and ingest them into the vector store for RAG.
    Accepts multiple files via multipart/form-data.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    document_loader = DocumentLoader()
    errors: List[str] = []
    processed_files: List[str] = []
    total_chunks = 0

    # Load the vector store once
    try:
        vector_db = VectorStoreLoader().load_vectorstore()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to vector store: {str(e)}"
        )

    tracker = _load_tracker()

    for upload_file in files:
        file_name = upload_file.filename or "unknown"
        save_path = UPLOAD_DIR / file_name

        try:
            # Ensure subdirectories exist (for folder uploads with paths)
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # Save file to disk
            with open(save_path, "wb") as f:
                content = await upload_file.read()
                f.write(content)

            print(f"📄 Processing: {file_name}")

            # Load and chunk the document
            docs = document_loader.load_documents(str(save_path))

            if docs:
                # Add to vector store
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

                print(f"  ✅ Added {chunk_count} chunks from {file_name}")
            else:
                errors.append(f"{file_name}: No content extracted")

        except Exception as e:
            error_msg = f"{file_name}: {str(e)}"
            errors.append(error_msg)
            print(f"  ❌ Error processing {file_name}: {e}")
            traceback.print_exc()

        finally:
            # Clean up temp file
            try:
                if save_path.exists():
                    save_path.unlink()
            except Exception:
                pass

    # Save the tracker
    _save_tracker(tracker)

    status = "success" if processed_files else "error"
    if processed_files and errors:
        status = "partial"

    return IngestResponse(
        status=status,
        message=f"Processed {len(processed_files)} file(s), {total_chunks} chunks added to knowledge base",
        files_processed=len(processed_files),
        total_chunks=total_chunks,
        documents=processed_files,
        errors=errors,
    )


@router.get("/status", response_model=IngestStatus)
async def get_ingest_status():
    """Get current ingestion status and document count."""
    tracker = _load_tracker()
    docs = tracker.get("documents", [])

    return IngestStatus(
        total_documents=len(docs),
        document_names=[d["name"] for d in docs],
        last_ingested=docs[-1]["ingested_at"] if docs else None,
    )


@router.get("/documents", response_model=List[DocumentInfo])
async def list_ingested_documents():
    """List all ingested documents with their details."""
    tracker = _load_tracker()
    docs = tracker.get("documents", [])

    return [
        DocumentInfo(
            name=d["name"],
            chunks=d["chunks"],
            ingested_at=d["ingested_at"],
            file_type=d.get("file_type", "unknown"),
        )
        for d in docs
    ]


@router.delete("/documents")
async def clear_knowledge_base():
    """Clear all documents from the knowledge base tracker.

    NOTE: This clears the tracker only.  Full PGVector collection
    clearing would require dropping and recreating the collection.
    """
    try:
        _save_tracker({"documents": []})

        return {
            "success": True,
            "message": "Knowledge base tracker cleared",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error clearing knowledge base: {str(e)}",
        )
