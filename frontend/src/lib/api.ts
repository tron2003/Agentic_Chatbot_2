const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001';

export interface ChatMessage {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: Date;
}

export interface ChatRequest {
  message: string;
  thread_id: string;
}

export interface ChatResponse {
  response: string;
}

export interface FileUploadRequest {
  message: string;
  thread_id: string;
  file_content?: string;
  file_name?: string;
  file_type?: string;
}

export async function sendMessage(request: ChatRequest): Promise<string> {
  const response = await fetch(`${API_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to send message');
  }

  const data: ChatResponse = await response.json();
  return data.response;
}

export async function getHealthStatus() {
  const response = await fetch(`${API_URL}/health`);
  if (!response.ok) throw new Error('Health check failed');
  return response.json();
}

export async function getChatHistory(chatId?: string) {
  const url = chatId
    ? `${API_URL}/api/history/chats/${chatId}`
    : `${API_URL}/api/history/chats`;

  const response = await fetch(url);
  if (!response.ok) throw new Error('Failed to fetch chat history');
  return response.json();
}

export async function saveChat(data: any) {
  const response = await fetch(`${API_URL}/api/history/chats`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) throw new Error('Failed to save chat');
  return response.json();
}
