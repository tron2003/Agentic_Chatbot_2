from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any

app = FastAPI(title="Agentic Chatbot API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    thread_id: str

class ChatResponse(BaseModel):
    response: str

@app.get("/")
async def root():
    return {"message": "Agentic Chatbot API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "chatbot_ready": True}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle chat requests from the frontend"""
    if not request.message or not request.thread_id:
        raise HTTPException(status_code=400, detail="Message and thread_id are required")
    
    try:
        # Simple echo response for testing
        response_content = f"You said: '{request.message}'. Thank you for your message! I'm a working chatbot API."
        
        return ChatResponse(response=response_content)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    
    # Run the server
    uvicorn.run(
        "test_backend:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )