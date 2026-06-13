from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, Optional, AsyncGenerator
from contextlib import asynccontextmanager
import asyncio
import sys
import io
import selectors
from pathlib import Path
import os
import logging
from datetime import datetime
import uuid
import json

# Configure logging
from agentic_chatbot.logging_config import configure_logging

environment = os.getenv("ENVIRONMENT", "production")
configure_logging(environment)

logger = logging.getLogger(__name__)

# Fix Windows console Unicode issues
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    # psycopg async requires SelectorEventLoop — Windows defaults to ProactorEventLoop
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    asyncio.set_event_loop(loop)

from langchain_core.messages import HumanMessage, BaseMessage

project_root = Path(__file__).parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))

from agentic_chatbot.mcp.mcp_manager import mcp_manager
from agentic_chatbot.components.memory import MemoryLoader
from agentic_chatbot.pipelines.chatbot_pipeline import ChatbotPipeline
from agentic_chatbot.utils.chat_persistence import get_persistence

# Import chat history routes
from routes.chat_history import router as chat_history_router

# Import document ingestion routes
from routes.ingest import router as ingest_router

# Define lifespan before creating the app
@asynccontextmanager
async def lifespan_context(app: FastAPI):
    """Handle startup and shutdown events"""
    global chatbot_instance, memory_loader

    # ── Startup ──
    try:
        log_dir = Path("artifacts/logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        await mcp_manager.initialize()

        memory_loader = MemoryLoader()
        checkpointer = await memory_loader.load_memory()

        chatbot_instance = ChatbotPipeline(checkpointer=checkpointer)

        print("\n✅ Chatbot API server started successfully on port 8001")
        print("📌 Available endpoints: /chat, /api/history/chats, /api/ingest/upload, /health\n")

    except Exception as e:
        logger.error(f"❌ Error during startup: {e}", exc_info=True)
        raise

    # ── Yield (server running) ──
    yield

    # ── Shutdown ──
    try:
        if memory_loader:
            await memory_loader.close()
            logger.info("Memory loader closed gracefully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


app = FastAPI(
    title="Agentic Chatbot API",
    version="1.0.0",
    description="Production-ready agentic chatbot with RAG, tool use, and conversation memory",
    lifespan=lifespan_context
)

# Configure CORS with environment-based origins
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://127.0.0.1:3000,http://127.0.0.1:3001,http://127.0.0.1:3002"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Include routers
app.include_router(chat_history_router)
app.include_router(ingest_router)

# Global variables
chatbot_instance = None
memory_loader = None

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000, description="User message")
    thread_id: str = Field(..., min_length=1, description="Conversation thread ID")

    @field_validator('message', mode='before')
    @classmethod
    def message_must_not_be_empty(cls, v):
        if isinstance(v, str) and not v.strip():
            raise ValueError('Message cannot be empty or whitespace only')
        return v if isinstance(v, str) else str(v)

class ChatResponse(BaseModel):
    response: str = Field(..., description="Assistant response")
    message_id: str = Field(..., description="Unique message ID")
    timestamp: str = Field(..., description="ISO 8601 timestamp")

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Agentic Chatbot API is running",
        "version": "1.0.0",
        "status": "healthy",
        "endpoints": {
            "chat": "/chat",
            "health": "/health",
            "chat_history": "/api/history/chats",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for deployment orchestration"""
    return {
        "status": "healthy",
        "chatbot_ready": chatbot_instance is not None,
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, request_obj: Request):
    """
    Send a message to the agentic chatbot and receive a response.

    The workflow:
    1. Persist user message to database
    2. Memory retrieval from PostgreSQL
    3. Router decision (Chat/RAG/Tool)
    4. Processing through appropriate node
    5. Response generation and storage
    """
    global chatbot_instance

    # Generate correlation ID for request tracking
    correlation_id = str(uuid.uuid4())
    request_obj.state.correlation_id = correlation_id

    if not chatbot_instance:
        logger.error(f"[{correlation_id}] Chatbot not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chatbot not initialized. Please try again later."
        )

    try:
        logger.info(f"[{correlation_id}] Received chat request - thread_id: {request.thread_id}, message_length: {len(request.message)}")

        # Generate IDs and timestamp
        user_message_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        # Persist user message to database
        persistence = await get_persistence()
        await persistence.ensure_table()
        user_saved = await persistence.save_message(
            chat_id=request.thread_id,
            message_id=user_message_id,
            role="user",
            content=request.message,
            timestamp=timestamp
        )
        if not user_saved:
            logger.warning(f"[{correlation_id}] Failed to persist user message to database")

        # Create the human message for the pipeline
        human_message = HumanMessage(content=request.message)

        # Run the chatbot pipeline
        result = await chatbot_instance.run(
            message=human_message,
            thread_id=request.thread_id
        )

        # Extract the response content
        response_content = result['messages'][-1].content if result['messages'] else "No response generated"
        assistant_message_id = str(uuid.uuid4())
        response_timestamp = datetime.utcnow().isoformat()

        # Persist assistant message to database
        assistant_saved = await persistence.save_message(
            chat_id=request.thread_id,
            message_id=assistant_message_id,
            role="assistant",
            content=response_content,
            timestamp=response_timestamp
        )
        if not assistant_saved:
            logger.warning(f"[{correlation_id}] Failed to persist assistant message to database")

        logger.info(f"[{correlation_id}] Chat response generated and persisted - response_id: {assistant_message_id}, response_length: {len(response_content)}")

        return ChatResponse(
            response=response_content,
            message_id=assistant_message_id,
            timestamp=response_timestamp
        )

    except ValueError as e:
        logger.warning(f"[{correlation_id}] Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request: {str(e)}"
        )
    except Exception as e:
        logger.error(f"[{correlation_id}] Error processing chat request: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request. Please try again."
        )

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, request_obj: Request):
    """
    Stream chat response with intermediate reasoning steps.
    Uses Server-Sent Events (SSE) to show thinking process like Claude Code.
    """
    global chatbot_instance

    correlation_id = str(uuid.uuid4())
    request_obj.state.correlation_id = correlation_id

    if not chatbot_instance:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chatbot not initialized. Please try again later."
        )

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            logger.info(f"[{correlation_id}] Streaming chat - thread_id: {request.thread_id}")

            # Generate IDs and timestamp
            user_message_id = str(uuid.uuid4())
            timestamp = datetime.utcnow().isoformat()

            # Message persistence handled by LangGraph checkpoint
            # (no need for separate chat_persistence since we have PostgreSQL checkpoint)

            # Create human message for pipeline
            human_message = HumanMessage(content=request.message)

            # Run the chatbot pipeline
            result = await chatbot_instance.run(
                message=human_message,
                thread_id=request.thread_id
            )

            # Extract response and reasoning steps
            response_content = result['messages'][-1].content if result['messages'] else "No response generated"

            # Get reasoning steps from message metadata
            final_message = result['messages'][-1] if result['messages'] else None
            reasoning_steps = []
            if final_message and hasattr(final_message, 'metadata') and final_message.metadata:
                reasoning_steps = final_message.metadata.get('reasoning_steps', [])

            # Stream reasoning steps (already dicts from ReasoningStep)
            for step in reasoning_steps:
                if isinstance(step, dict):
                    event = f"data: {json.dumps({'type': 'reasoning_step', 'data': step})}\n\n"
                    yield event

            # Stream final response
            assistant_message_id = str(uuid.uuid4())
            response_timestamp = datetime.utcnow().isoformat()

            response_event = {
                "type": "response",
                "data": {
                    "response": response_content,
                    "message_id": assistant_message_id,
                    "timestamp": response_timestamp
                }
            }
            yield f"data: {json.dumps(response_event)}\n\n"

            logger.info(f"[{correlation_id}] Streaming complete - {len(reasoning_steps)} steps")

            # Send complete event
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except ValueError as e:
            logger.warning(f"[{correlation_id}] Validation error: {e}")
            error_event = {
                "type": "error",
                "data": {"detail": f"Invalid request: {str(e)}"}
            }
            yield f"data: {json.dumps(error_event)}\n\n"
        except Exception as e:
            logger.error(f"[{correlation_id}] Error in stream: {e}", exc_info=True)
            error_event = {
                "type": "error",
                "data": {"detail": "An error occurred while processing your request."}
            }
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Global exception handler to prevent stack trace leakage"""
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    logger.error(f"[{correlation_id}] Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again later."}
    )

if __name__ == "__main__":
    import uvicorn

    # Configuration from environment or defaults
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "8001"))
    workers = int(os.getenv("SERVER_WORKERS", "1"))
    reload = os.getenv("SERVER_RELOAD", "false").lower() == "true"

    logger.info(f"🚀 Starting Agentic Chatbot API on {host}:{port}")

    uvicorn.run(
        "backend_api:app",
        host=host,
        port=port,
        workers=workers,
        reload=reload,
        log_level="info",
        access_log=True
    )
