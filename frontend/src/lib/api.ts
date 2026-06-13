export const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8001';

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

export async function sendMessage(request: ChatRequest): Promise<string> {
  const response = await fetch(`${API_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to send message' }));
    throw new Error(error.detail || 'Failed to send message');
  }

  const data: ChatResponse = await response.json();
  return data.response;
}

export interface ReasoningStep {
  type: 'thinking' | 'tool_call' | 'tool_result' | 'final_answer';
  content: string;
  timestamp: string;
}

export interface StreamEvent {
  type: 'reasoning_step' | 'response' | 'error' | 'complete';
  data?: any;
}

/**
 * Stream chat response with reasoning steps (SSE).
 * Yields events as the agent thinks and takes actions.
 */
export async function* streamMessage(
  request: ChatRequest
): AsyncGenerator<StreamEvent, void, unknown> {
  const response = await fetch(`${API_URL}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to send message' }));
    throw new Error(error.detail || 'Failed to send message');
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');

      // Keep the last incomplete line in the buffer
      buffer = lines[lines.length - 1];

      for (let i = 0; i < lines.length - 1; i++) {
        const line = lines[i].trim();
        if (line.startsWith('data: ')) {
          try {
            const eventData = JSON.parse(line.slice(6));
            yield eventData as StreamEvent;
          } catch (e) {
            console.error('Failed to parse SSE event:', e);
          }
        }
      }
    }

    // Process any remaining data
    if (buffer.trim().startsWith('data: ')) {
      try {
        const eventData = JSON.parse(buffer.trim().slice(6));
        yield eventData as StreamEvent;
      } catch (e) {
        console.error('Failed to parse final SSE event:', e);
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export async function getHealthStatus() {
  const response = await fetch(`${API_URL}/health`);
  if (!response.ok) throw new Error('Health check failed');
  return response.json();
}

export async function getChatHistory() {
  const response = await fetch(`${API_URL}/api/history/chats`);
  if (!response.ok) throw new Error('Failed to fetch chat history');
  return response.json();
}

export async function getChatById(chatId: string) {
  const response = await fetch(`${API_URL}/api/history/chats/${chatId}`);
  if (!response.ok) throw new Error('Failed to fetch chat');
  return response.json();
}

export async function saveChat(data: any) {
  const response = await fetch(`${API_URL}/api/history/chats`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to save chat');
  return response.json();
}

export async function deleteChat(chatId: string) {
  const response = await fetch(`${API_URL}/api/history/chats/${chatId}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete chat');
  return response.json();
}

// ── Document Ingestion API ───────────────────────────────────────────────────

export interface IngestResponse {
  status: 'success' | 'partial' | 'error';
  message: string;
  files_processed: number;
  total_chunks: number;
  documents: string[];
  errors: string[];
}

export interface IngestStatus {
  total_documents: number;
  document_names: string[];
  last_ingested: string | null;
}

export interface DocumentInfo {
  name: string;
  chunks: number;
  ingested_at: string;
  file_type: string;
}

/**
 * Upload files to the backend for ingestion into the vector store.
 * Uses multipart/form-data.
 */
export async function uploadDocuments(files: File[]): Promise<IngestResponse> {
  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file);
  }

  const response = await fetch(`${API_URL}/api/ingest/upload`, {
    method: 'POST',
    body: formData,
    // No Content-Type header — browser sets it automatically with boundary
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(error.detail || 'Failed to upload documents');
  }

  return response.json();
}

/** Get ingestion status (total documents, last ingested time). */
export async function getIngestStatus(): Promise<IngestStatus> {
  const response = await fetch(`${API_URL}/api/ingest/status`);
  if (!response.ok) throw new Error('Failed to fetch ingest status');
  return response.json();
}

/** List all ingested documents with chunk counts. */
export async function getIngestedDocuments(): Promise<DocumentInfo[]> {
  const response = await fetch(`${API_URL}/api/ingest/documents`);
  if (!response.ok) throw new Error('Failed to fetch documents');
  return response.json();
}

/** Clear all documents from the knowledge base. */
export async function clearKnowledgeBase(): Promise<void> {
  const response = await fetch(`${API_URL}/api/ingest/documents`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to clear knowledge base');
}
