from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any
import asyncio
import sys
import io
import selectors
from pathlib import Path

# Fix Windows console Unicode issues
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    # psycopg async requires SelectorEventLoop — Windows defaults to ProactorEventLoop
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    asyncio.set_event_loop(loop)

from langchain_core.messages import HumanMessage

project_root = Path(__file__).parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))

from agentic_chatbot.mcp.mcp_manager import mcp_manager
from agentic_chatbot.components.memory import MemoryLoader
from agentic_chatbot.pipelines.chatbot_pipeline import ChatbotPipeline

# Import chat history routes
from routes.chat_history import router as chat_history_router

app = FastAPI(title="Agentic Chatbot API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
    ],  # Next.js dev server on various ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include chat history routes
app.include_router(chat_history_router)

# Global variables to store the chatbot instance
chatbot_instance = None
memory_loader = None

class ChatRequest(BaseModel):
    message: str
    thread_id: str

class ChatResponse(BaseModel):
    response: str

@app.on_event("startup")
async def startup_event():
    """Initialize the chatbot when the server starts"""
    global chatbot_instance, memory_loader
    
    try:
        # Initialize MCP manager
        await mcp_manager.initialize()
        
        # Load memory and create chatbot instance
        memory_loader = MemoryLoader()
        checkpointer = await memory_loader.load_memory()
        
        chatbot_instance = ChatbotPipeline(checkpointer=checkpointer)
        
        print("✅ Chatbot API server started successfully on port 8001")
        print("📌 Available endpoints:")
        print("   - POST /chat - Send message to chatbot")
        print("   - GET /api/history/chats - Get chat history")
        print("   - GET /api/history/chats/{chat_id} - Get specific chat")
        print("   - POST /api/history/chats - Save chat")
        print("   - DELETE /api/history/chats/{chat_id} - Delete chat")
        
    except Exception as e:
        print(f"❌ Error during startup: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources when the server shuts down"""
    global memory_loader
    
    if memory_loader:
        await memory_loader.close()
        print("Memory loader closed")

@app.get("/")
async def root():
    return {
        "message": "Agentic Chatbot API is running",
        "version": "1.0.0",
        "status": "healthy",
        "endpoints": {
            "chat": "/chat",
            "health": "/health",
            "chat_history": "/api/history/chats"
        }
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "chatbot_ready": chatbot_instance is not None,
        "server_port": 8001
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle chat requests from the frontend"""
    global chatbot_instance
    
    if not chatbot_instance:
        raise HTTPException(status_code=503, detail="Chatbot not initialized")
    
    if not request.message or not request.thread_id:
        raise HTTPException(status_code=400, detail="Message and thread_id are required")
    
    try:
        # Create the human message
        human_message = HumanMessage(content=request.message)
        
        # Run the chatbot pipeline
        result = await chatbot_instance.run(
            message=human_message,
            thread_id=request.thread_id
        )
        
        # Extract the response content
        response_content = result['messages'][-1].content
        
        return ChatResponse(response=response_content)
        
    except Exception as e:
        print(f"Error processing chat request: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    
    # Run the server on port 8001
    print("🚀 Starting Agentic Chatbot API...")
    uvicorn.run(
        "backend_api:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info"
    )
