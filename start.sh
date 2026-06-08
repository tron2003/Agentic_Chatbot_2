#!/bin/bash

# Agentic Chatbot - Startup Script for macOS/Linux
# This script starts both frontend and backend servers

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║          AGENTIC CHATBOT - STARTUP SCRIPT v1.0                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if running from project root
if [ ! -f "backend_api.py" ]; then
    echo "❌ Error: backend_api.py not found"
    echo "Please run this script from the project root directory"
    exit 1
fi

if [ ! -f "frontend/package.json" ]; then
    echo "❌ Error: frontend directory not found"
    echo "Please run this script from the project root directory"
    exit 1
fi

# Check if virtual environment exists
if [ ! -f "venv/bin/activate" ]; then
    echo "❌ Error: Virtual environment not found"
    echo "Please create it first with: python3 -m venv venv"
    exit 1
fi

echo "✅ Project structure verified"
echo ""
echo "📋 Starting services..."
echo ""

# Activate virtual environment
source venv/bin/activate

# Start backend in the background
echo "🚀 Starting Backend API (port 8001)..."
python backend_api.py &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"

# Wait a moment for backend to start
sleep 3

# Start frontend in the background
echo "🚀 Starting Frontend (Next.js)..."
cd frontend
npm run dev &
FRONTEND_PID=$!
echo "   Frontend PID: $FRONTEND_PID"
cd ..

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                  SERVICES STARTED                              ║"
echo "╠════════════════════════════════════════════════════════════════╣"
echo "║  Backend:  http://localhost:8001                               ║"
echo "║  Frontend: http://localhost:3002 (or next available port)      ║"
echo "║                                                                ║"
echo "║  Chat API:     POST http://localhost:8001/chat                ║"
echo "║  Health:       GET  http://localhost:8001/health              ║"
echo "║  Chat History: GET  http://localhost:8001/api/history/chats   ║"
echo "║                                                                ║"
echo "║  Backend PID:  $BACKEND_PID                                            ║"
echo "║  Frontend PID: $FRONTEND_PID                                            ║"
echo "║                                                                ║"
echo "║  To stop services, use:                                        ║"
echo "║    kill $BACKEND_PID   (stop backend)                         ║"
echo "║    kill $FRONTEND_PID  (stop frontend)                        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Press Ctrl+C to stop all services..."

# Wait for both processes
wait
