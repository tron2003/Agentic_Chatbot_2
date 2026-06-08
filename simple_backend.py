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

# Simple MCP manager that doesn't require initialization
class SimpleMCPManager:
    def __init__(self):
        pass
    
    async def initialize(self):
        print("Simple MCP manager initialized")
        pass

app = FastAPI(title="Agentic Chatbot API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3002", "http://127.0.0.1:3002", "http://localhost:3002"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables to store the chatbot instance
chatbot_instance = None
memory_loader = None
mcp_manager = SimpleMCPManager()

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
        
        # Try to import and initialize the chatbot components
        try:
            from agentic_chatbot.components.memory import MemoryLoader
            from agentic_chatbot.pipelines.chatbot_pipeline import ChatbotPipeline
            
            # Load memory and create chatbot instance
            memory_loader = MemoryLoader()
            checkpointer = await memory_loader.load_memory()
            
            chatbot_instance = ChatbotPipeline(checkpointer=checkpointer)
            
            print("Chatbot API server started successfully")
            
        except Exception as e:
            print(f"Error initializing chatbot: {e}")
            print("Running in fallback mode with simple echo response")
            chatbot_instance = None
            
    except Exception as e:
        print(f"Error during startup: {e}")
        chatbot_instance = None

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources when the server shuts down"""
    global memory_loader
    
    if memory_loader:
        await memory_loader.close()
        print("Memory loader closed")

@app.get("/")
async def root():
    return {"message": "Agentic Chatbot API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "chatbot_ready": chatbot_instance is not None}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle chat requests from the frontend"""
    global chatbot_instance
    
    if not request.message or not request.thread_id:
        raise HTTPException(status_code=400, detail="Message and thread_id are required")
    
    try:
        if chatbot_instance:
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
        else:
            # Fallback response
            fallback_responses = [
                "Hello! I'm the agentic chatbot. I'm currently running in fallback mode.",
                "I'm ready to help you! My full capabilities will be available once the backend services are properly initialized.",
                "Hi there! I'm your AI assistant. I can help you with various tasks using my advanced capabilities.",
                "Welcome! I'm the agentic chatbot. I'm currently in setup mode but ready to assist you.",
                "Hello! I'm your AI companion. I have access to various tools and memory features."
            ]
            
            import random
            response_content = random.choice(fallback_responses)
            
            return ChatResponse(response=response_content)
        
    except Exception as e:
        print(f"Error processing chat request: {e}")
        # Return a safe error response
        return ChatResponse(response=f"I apologize, but I encountered an error: {str(e)}. Please try again.")

if __name__ == "__main__":
    import uvicorn
    
    # Run the server
    uvicorn.run(
        "simple_backend:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info"
    )