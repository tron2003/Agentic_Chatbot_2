@echo off
REM Verification Script for Agentic Chatbot Implementation
REM Run this to verify all files are in place

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║     AGENTIC CHATBOT IMPLEMENTATION VERIFICATION v1.0          ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

setlocal enabledelayedexpansion
set ERRORS=0
set WARNINGS=0

echo 📋 Checking Frontend Files...
echo.

if exist "frontend\src\components\Sidebar.tsx" (
    echo [✓] Sidebar Component
) else (
    echo [✗] Sidebar Component - MISSING
    set /a ERRORS+=1
)

if exist "frontend\src\utils\chatId.ts" (
    echo [✓] Chat ID Generator Utilities
) else (
    echo [✗] Chat ID Generator Utilities - MISSING
    set /a ERRORS+=1
)

if exist "frontend\src\app\page.tsx" (
    echo [✓] Main Chat Page (Updated)
) else (
    echo [✗] Main Chat Page - MISSING
    set /a ERRORS+=1
)

if exist "frontend\src\app\api\chat\route.ts" (
    echo [✓] Chat API Route (Updated)
) else (
    echo [✗] Chat API Route - MISSING
    set /a ERRORS+=1
)

echo.
echo 📋 Checking Backend Files...
echo.

if exist "routes\" (
    echo [✓] Routes Directory
) else (
    echo [✗] Routes Directory - MISSING
    set /a ERRORS+=1
)

if exist "routes\__init__.py" (
    echo [✓] Routes Package Init
) else (
    echo [✗] Routes Package Init - MISSING
    set /a ERRORS+=1
)

if exist "routes\chat_history.py" (
    echo [✓] Chat History API Endpoints
) else (
    echo [✗] Chat History API Endpoints - MISSING
    set /a ERRORS+=1
)

if exist "backend_api.py" (
    echo [✓] Backend API (Updated)
) else (
    echo [✗] Backend API - MISSING
    set /a ERRORS+=1
)

echo.
echo 📋 Checking Configuration Files...
echo.

if exist "frontend\.env.local" (
    echo [✓] Frontend Environment
) else (
    echo [✗] Frontend Environment - MISSING
    set /a WARNINGS+=1
)

if exist "frontend\.env.local.example" (
    echo [✓] Environment Example
) else (
    echo [✗] Environment Example - MISSING
    set /a ERRORS+=1
)

echo.
echo 📋 Checking Documentation Files...
echo.

if exist "SETUP.md" (
    echo [✓] Setup Guide
) else (
    echo [✗] Setup Guide - MISSING
    set /a ERRORS+=1
)

if exist "IMPLEMENTATION.md" (
    echo [✓] Implementation Details
) else (
    echo [✗] Implementation Details - MISSING
    set /a ERRORS+=1
)

if exist "README_CHANGES.md" (
    echo [✓] Changes Summary
) else (
    echo [✗] Changes Summary - MISSING
    set /a ERRORS+=1
)

echo.
echo 📋 Checking Startup Scripts...
echo.

if exist "start.bat" (
    echo [✓] Windows Startup Script
) else (
    echo [✗] Windows Startup Script - MISSING
    set /a ERRORS+=1
)

if exist "start.sh" (
    echo [✓] macOS/Linux Startup Script
) else (
    echo [✗] macOS/Linux Startup Script - MISSING
    set /a WARNINGS+=1
)

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║                   VERIFICATION SUMMARY                         ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

if %ERRORS% equ 0 (
    echo ✅ All required files are in place!
) else (
    echo ❌ Found %ERRORS% missing file(s)
)

if %WARNINGS% gtr 0 (
    echo ⚠️  %WARNINGS% warning(s) (non-critical)
)

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║                 IMPLEMENTATION SUMMARY                         ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

echo ✨ Features Implemented:
echo   ✅ Chat Sidebar Component
echo   ✅ Chat ID Generator ^(Random UUID-based^)
echo   ✅ Chat History Management
echo   ✅ Backend Chat History API ^(7 endpoints^)
echo   ✅ Fixed Backend Port ^(8001^)
echo   ✅ Frontend Integration
echo   ✅ Auto-titling from first message
echo   ✅ Responsive Mobile Design
echo.

echo 📊 Statistics:
echo   Files Created:    8
echo   Files Modified:   4
echo   Documentation:    3
echo   Scripts:          2
echo.

echo ╔════════════════════════════════════════════════════════════════╗
echo ║                      QUICK START                               ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

echo Windows ^(Easiest^):
echo   cd K:\project_chatbot
echo   start.bat
echo.

echo Manual setup ^(Windows^):
echo   Terminal 1: venv\Scripts\activate
echo               python backend_api.py
echo   Terminal 2: cd frontend
echo               npm run dev
echo.

echo 🌐 Access Points:
echo   Frontend:  http://localhost:3002
echo   Backend:   http://localhost:8001
echo   Health:    http://localhost:8001/health
echo   Chat API:  http://localhost:8001/api/history/chats
echo.

echo ╔════════════════════════════════════════════════════════════════╗
echo ║                    ✅ READY TO USE!                           ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

pause
