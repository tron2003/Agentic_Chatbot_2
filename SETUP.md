# Agentic Chatbot - Setup Guide

## 📋 Overview

This is a full-stack AI chatbot application with:
- **Frontend**: Next.js React application with a modern UI and sidebar for chat history
- **Backend**: FastAPI server with chat management endpoints
- **Features**: 
  - Chat history with persistent storage
  - Random chat ID generation for unique conversations
  - Sidebar navigation with chat management
  - Real-time message display
  - Error handling and status indicators

## 🚀 Quick Start

### Prerequisites
- Python 3.8+ (for backend)
- Node.js 16+ (for frontend)
- pip and npm package managers

### 1. Backend Setup

**Step 1: Navigate to project root**
```bash
cd K:\project_chatbot
```

**Step 2: Activate virtual environment**
```bash
# On Windows
venv\Scripts\activate

# On macOS/Linux
source venv/bin/activate
```

**Step 3: Start the backend server**
```bash
python backend_api.py
```

The backend should start on `http://localhost:8001`

**Expected output:**
```
🚀 Starting Agentic Chatbot API...
✅ Chatbot API server started successfully on port 8001
📌 Available endpoints:
   - POST /chat - Send message to chatbot
   - GET /api/history/chats - Get chat history
   - GET /api/history/chats/{chat_id} - Get specific chat
   - POST /api/history/chats - Save chat
   - DELETE /api/history/chats/{chat_id} - Delete chat
```

### 2. Frontend Setup

**Step 1: Navigate to frontend directory**
```bash
cd K:\project_chatbot\frontend
```

**Step 2: Install dependencies**
```bash
npm install
```

**Step 3: Configure environment (if needed)**
Make sure `.env.local` has:
```
BACKEND_URL=http://localhost:8001
```

**Step 4: Start development server**
```bash
npm run dev
```

The frontend will start on `http://localhost:3002` (or the next available port)

## 📁 Project Structure

```
project_chatbot/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx          # Main chat page
│   │   │   ├── layout.tsx        # Root layout
│   │   │   └── api/chat/route.ts # Chat API proxy
│   │   ├── components/
│   │   │   └── Sidebar.tsx       # Chat sidebar component
│   │   └── utils/
│   │       └── chatId.ts         # Chat ID generator utilities
│   ├── package.json
│   └── .env.local                # Backend URL configuration
│
├── routes/
│   ├── __init__.py
│   └── chat_history.py           # Chat history management endpoints
│
├── backend_api.py                 # FastAPI server
├── app/main.py                    # CLI version
└── README.md                       # This file
```

## 🔧 Key Features Explained

### Chat ID Generator (`frontend/src/utils/chatId.ts`)
Generates unique chat IDs with format: `chat_[uuid]_[timestamp]`

**Functions:**
- `generateChatId()` - Create new unique chat ID
- `generateUUID()` - RFC 4122 compliant UUID
- `formatChatIdForDisplay()` - Show last 8 chars of UUID
- `getChatDisplayName()` - Create title from first message
- `formatChatDate()` - Format date for UI display

### Sidebar Component (`frontend/src/components/Sidebar.tsx`)
- Dark-themed navigation sidebar
- Chat history list with timestamps
- Delete chat functionality
- "New Chat" button
- Mobile responsive design

### Chat History Management (`routes/chat_history.py`)
**Endpoints:**
- `GET /api/history/chats` - List all chats
- `GET /api/history/chats/{chat_id}` - Get specific chat
- `POST /api/history/chats` - Save/update chat
- `PUT /api/history/chats/{chat_id}/title` - Update title
- `DELETE /api/history/chats/{chat_id}` - Delete chat
- `DELETE /api/history/chats` - Clear all chats
- `GET /api/history/stats` - Get chat statistics

## 💾 Data Storage

### Frontend (Browser)
- Uses localStorage for client-side persistence
- Stores chat history and messages locally
- No backend sync required for basic functionality

### Backend (Server)
- File-based storage in `chat_data/` directory
- Optional: Can be replaced with MongoDB/PostgreSQL
- Automatic file creation and management

## 🔌 API Reference

### Chat Endpoint
```
POST /chat
Content-Type: application/json

Request:
{
  "message": "Hello, how are you?",
  "thread_id": "chat_xxx-xxx_timestamp"
}

Response:
{
  "response": "I'm doing well, thank you for asking!"
}
```

### Chat History Endpoints
```
GET /api/history/chats
GET /api/history/chats/{chat_id}
POST /api/history/chats
PUT /api/history/chats/{chat_id}/title
DELETE /api/history/chats/{chat_id}
```

## 🐛 Troubleshooting

### Backend not connecting (ECONNREFUSED 127.0.0.1:8001)
- Make sure backend is running: `python backend_api.py`
- Check that port 8001 is not in use
- Verify `BACKEND_URL` in frontend `.env.local`

### Port already in use
```bash
# Find process using port 8001 and kill it
# Windows:
netstat -ano | findstr :8001

# macOS/Linux:
lsof -i :8001
```

### Chat history not loading
- Check browser localStorage (DevTools > Application > Local Storage)
- Ensure JavaScript is enabled
- Clear cache if issues persist

### Frontend build issues
```bash
cd frontend
rm -rf node_modules .next
npm install
npm run dev
```

## 📝 Next Steps

1. **Database Integration**: Replace file-based storage with proper database
2. **User Authentication**: Add login/logout functionality
3. **Chat Sharing**: Enable sharing chat transcripts
4. **Advanced Analytics**: Track chat statistics and metrics
5. **Model Selection**: Add ability to choose different AI models

## 📄 License

This project is part of the Agentic Chatbot system.

## 🤝 Support

For issues or questions:
1. Check the troubleshooting section
2. Review backend logs on port 8001
3. Check browser console for frontend errors

---

**Version**: 1.0.0  
**Last Updated**: 2026-06-09
