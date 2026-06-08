"""
Chat History Router
Handles chat history endpoints for managing conversations
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
from pathlib import Path

router = APIRouter(prefix="/api/history", tags=["history"])

# In-memory storage for chat history (can be replaced with database)
chat_storage: Dict[str, Dict[str, Any]] = {}

# Optional: Use file-based storage
STORAGE_DIR = Path("chat_data")
STORAGE_DIR.mkdir(exist_ok=True)

class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: str

class ChatSession(BaseModel):
    chat_id: str
    title: str
    created_at: str
    messages: List[ChatMessage]

class ChatHistoryItem(BaseModel):
    chat_id: str
    title: str
    created_at: str
    message_count: int

class SaveChatRequest(BaseModel):
    chat_id: str
    title: str
    messages: List[ChatMessage]

class UpdateChatTitleRequest(BaseModel):
    chat_id: str
    title: str

@router.get("/chats", response_model=List[ChatHistoryItem])
async def get_chat_history():
    """Get list of all chats"""
    history = []
    
    # Load from storage files
    for chat_file in STORAGE_DIR.glob("chat_*.json"):
        try:
            with open(chat_file, 'r') as f:
                data = json.load(f)
                history.append(ChatHistoryItem(
                    chat_id=data['chat_id'],
                    title=data['title'],
                    created_at=data['created_at'],
                    message_count=len(data.get('messages', []))
                ))
        except Exception as e:
            print(f"Error loading chat file {chat_file}: {e}")
    
    # Sort by creation date (newest first)
    history.sort(key=lambda x: x.created_at, reverse=True)
    return history

@router.get("/chats/{chat_id}", response_model=ChatSession)
async def get_chat(chat_id: str):
    """Get a specific chat session"""
    chat_file = STORAGE_DIR / f"chat_{chat_id}.json"
    
    if not chat_file.exists():
        raise HTTPException(status_code=404, detail="Chat not found")
    
    try:
        with open(chat_file, 'r') as f:
            data = json.load(f)
            return ChatSession(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading chat: {str(e)}")

@router.post("/chats")
async def save_chat(request: SaveChatRequest):
    """Save or update a chat session"""
    chat_file = STORAGE_DIR / f"chat_{request.chat_id}.json"
    
    try:
        chat_data = {
            "chat_id": request.chat_id,
            "title": request.title,
            "created_at": datetime.now().isoformat() if not chat_file.exists() else None,
            "updated_at": datetime.now().isoformat(),
            "messages": [msg.dict() for msg in request.messages]
        }
        
        # Preserve created_at if updating
        if chat_file.exists():
            with open(chat_file, 'r') as f:
                existing = json.load(f)
                chat_data["created_at"] = existing.get("created_at", datetime.now().isoformat())
        else:
            chat_data["created_at"] = datetime.now().isoformat()
        
        with open(chat_file, 'w') as f:
            json.dump(chat_data, f, indent=2)
        
        return {
            "success": True,
            "chat_id": request.chat_id,
            "message": "Chat saved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving chat: {str(e)}")

@router.put("/chats/{chat_id}/title")
async def update_chat_title(chat_id: str, request: UpdateChatTitleRequest):
    """Update chat title"""
    chat_file = STORAGE_DIR / f"chat_{chat_id}.json"
    
    if not chat_file.exists():
        raise HTTPException(status_code=404, detail="Chat not found")
    
    try:
        with open(chat_file, 'r') as f:
            data = json.load(f)
        
        data['title'] = request.title
        data['updated_at'] = datetime.now().isoformat()
        
        with open(chat_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        return {
            "success": True,
            "chat_id": chat_id,
            "title": request.title
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating title: {str(e)}")

@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str):
    """Delete a chat session"""
    chat_file = STORAGE_DIR / f"chat_{chat_id}.json"
    
    if not chat_file.exists():
        raise HTTPException(status_code=404, detail="Chat not found")
    
    try:
        chat_file.unlink()  # Delete file
        return {
            "success": True,
            "chat_id": chat_id,
            "message": "Chat deleted successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting chat: {str(e)}")

@router.delete("/chats")
async def clear_all_chats():
    """Delete all chat sessions"""
    try:
        count = 0
        for chat_file in STORAGE_DIR.glob("chat_*.json"):
            chat_file.unlink()
            count += 1
        
        return {
            "success": True,
            "deleted_count": count,
            "message": f"Deleted {count} chat(s)"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing chats: {str(e)}")

@router.get("/stats")
async def get_chat_stats():
    """Get chat statistics"""
    chat_files = list(STORAGE_DIR.glob("chat_*.json"))
    total_messages = 0
    total_chats = len(chat_files)
    
    for chat_file in chat_files:
        try:
            with open(chat_file, 'r') as f:
                data = json.load(f)
                total_messages += len(data.get('messages', []))
        except:
            pass
    
    return {
        "total_chats": total_chats,
        "total_messages": total_messages,
        "average_messages_per_chat": total_messages / total_chats if total_chats > 0 else 0
    }
