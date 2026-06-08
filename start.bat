@echo off
REM Agentic Chatbot - Startup Script for Windows
REM This script starts both frontend and backend servers

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║          AGENTIC CHATBOT - STARTUP SCRIPT v1.0                ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

REM Check if running from project root
if not exist "backend_api.py" (
    echo ❌ Error: backend_api.py not found
    echo Please run this script from the project root directory (K:\project_chatbot)
    pause
    exit /b 1
)

if not exist "frontend\package.json" (
    echo ❌ Error: frontend directory not found
    echo Please run this script from the project root directory (K:\project_chatbot)
    pause
    exit /b 1
)

REM Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo ❌ Error: Virtual environment not found
    echo Please create it first with: python -m venv venv
    pause
    exit /b 1
)

echo ✅ Project structure verified
echo.
echo 📋 Starting services...
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Start backend in a new window
echo 🚀 Starting Backend API (port 8001)...
echo.
start "Backend API - Agentic Chatbot" cmd /k python backend_api.py

REM Wait a moment for backend to start
timeout /t 3 /nobreak

REM Start frontend in a new window
echo 🚀 Starting Frontend (Next.js)...
echo.
cd frontend
start "Frontend - Agentic Chatbot" cmd /k npm run dev
cd ..

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║                  SERVICES STARTED                              ║
echo ╠════════════════════════════════════════════════════════════════╣
echo ║  Backend:  http://localhost:8001                               ║
echo ║  Frontend: http://localhost:3002 (or next available port)      ║
echo ║                                                                ║
echo ║  Chat API:     POST http://localhost:8001/chat                ║
echo ║  Health:       GET  http://localhost:8001/health              ║
echo ║  Chat History: GET  http://localhost:8001/api/history/chats   ║
echo ║                                                                ║
echo ║  Press Ctrl+C in either window to stop the respective service ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

REM Keep the main window open
pause
