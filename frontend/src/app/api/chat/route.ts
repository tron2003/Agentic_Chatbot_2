import { NextRequest, NextResponse } from 'next/server'

interface ChatRequest {
  message: string
  thread_id: string
}

interface ChatResponse {
  response: string
}

export async function POST(request: NextRequest) {
  try {
    const body: ChatRequest = await request.json()
    const { message, thread_id } = body

    if (!message || !thread_id) {
      return NextResponse.json(
        { error: 'Message and thread_id are required' },
        { status: 400 }
      )
    }

    // Create a proxy to the backend chatbot API
    // Updated: Backend is running on port 8001, not 8000
    const backendUrl = `${process.env.BACKEND_URL || 'http://localhost:8001'}/chat`
    
    console.log(`Sending chat request to backend: ${backendUrl}`)
    console.log(`Message: ${message}`)
    console.log(`Thread ID: ${thread_id}`)

    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message,
        thread_id,
      }),
    })

    if (!response.ok) {
      const errorText = await response.text()
      console.error('Backend error:', errorText)
      return NextResponse.json(
        { error: `Backend request failed: ${response.status} - ${errorText}` },
        { status: response.status }
      )
    }

    const data: ChatResponse = await response.json()
    
    return NextResponse.json(data)
    
  } catch (error) {
    console.error('Chat API error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
