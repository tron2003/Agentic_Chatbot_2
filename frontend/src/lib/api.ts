import type {
  ChatMode,
  Conversation,
  DocumentInfo,
  MemoryItem,
  MemoryList,
  Meta,
  ModelCatalog,
  ModelChoice,
  ModelCurrent,
  StoredMessage,
  StreamEvent,
  UploadResponse,
} from './types';

/** Empty in production (same origin as the API); set VITE_API_URL to call a separate host. */
export const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? '';

const KEY_STORAGE = 'junction.apiKey';

export function getApiKey(): string | null {
  try {
    return localStorage.getItem(KEY_STORAGE);
  } catch {
    return null;
  }
}

export function setApiKey(key: string | null) {
  try {
    if (key) localStorage.setItem(KEY_STORAGE, key);
    else localStorage.removeItem(KEY_STORAGE);
  } catch {
    /* storage unavailable */
  }
}

export class ApiError extends Error {
  status: number;
  code: string;
  requestId?: string;
  constructor(message: string, status: number, code = 'ERROR', requestId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

function headers(extra: Record<string, string> = {}): Record<string, string> {
  const h: Record<string, string> = { ...extra };
  const key = getApiKey();
  if (key) h.Authorization = `Bearer ${key}`;
  return h;
}

async function toError(res: Response): Promise<ApiError> {
  let message = `Request failed (${res.status})`;
  let code = `HTTP_${res.status}`;
  let requestId = res.headers.get('x-request-id') ?? undefined;
  try {
    const body = await res.json();
    message = body?.error?.message ?? body?.detail ?? message;
    code = body?.error?.code ?? code;
    requestId = body?.error?.request_id ?? requestId;
  } catch {
    /* non-JSON error body */
  }
  if (res.status === 0 || res.status === 502 || res.status === 504) {
    message = "Can't reach the server. Is the backend running?";
  }
  return new ApiError(message, res.status, code, requestId);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: headers({
        ...(init.body && !(init.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
        ...((init.headers as Record<string, string>) ?? {}),
      }),
    });
  } catch {
    throw new ApiError("Can't reach the server. Is the backend running?", 0, 'NETWORK');
  }
  if (!res.ok) throw await toError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  meta: () => request<Meta>('/api/meta'),
  conversations: (q?: string) =>
    request<Conversation[]>(`/api/conversations${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  conversation: (id: string) =>
    request<{ conversation: Conversation; messages: StoredMessage[] }>(`/api/conversations/${encodeURIComponent(id)}`),
  rename: (id: string, title: string) =>
    request<Conversation>(`/api/conversations/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),
  remove: (id: string) => request<void>(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  documents: () => request<DocumentInfo[]>('/api/documents'),
  removeDocument: (id: string) => request<void>(`/api/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  clearDocuments: () => request<{ deleted: number }>('/api/documents?confirm=true', { method: 'DELETE' }),
  upload: (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append('files', f, f.name));
    return request<UploadResponse>('/api/documents', { method: 'POST', body: form });
  },
  models: (refresh = false) => request<ModelCatalog>(`/api/models${refresh ? '?refresh=true' : ''}`),
  setModels: (main: ModelChoice, router: ModelChoice | null) =>
    request<ModelCurrent>('/api/models', { method: 'PUT', body: JSON.stringify({ main, router }) }),
  resetModels: () => request<ModelCurrent>('/api/models', { method: 'DELETE' }),
  memories: () => request<MemoryList>('/api/memory'),
  addMemory: (content: string) => request<MemoryItem>('/api/memory', { method: 'POST', body: JSON.stringify({ content }) }),
  removeMemory: (id: string) => request<void>(`/api/memory/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  clearMemories: () => request<{ deleted: number }>('/api/memory?confirm=true', { method: 'DELETE' }),
  exportUrl: (id: string) => `${API_URL}/api/conversations/${encodeURIComponent(id)}/export`,
  /** One answer (a Deep research report) as a PDF file. */
  async exportPdf(conversationId: string, messageId: string): Promise<{ filename: string; blob: Blob }> {
    const url = `${API_URL}/api/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}/pdf`;
    let res: Response;
    try {
      res = await fetch(url, { headers: headers() });
    } catch {
      throw new ApiError("Can't reach the server. Is the backend running?", 0, 'NETWORK');
    }
    if (!res.ok) throw await toError(res);
    const disposition = res.headers.get('content-disposition') ?? '';
    const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'report.pdf';
    return { filename, blob: await res.blob() };
  },
  async exportMarkdown(id: string): Promise<{ filename: string; text: string }> {
    const res = await fetch(this.exportUrl(id), { headers: headers() });
    if (!res.ok) throw await toError(res);
    const disposition = res.headers.get('content-disposition') ?? '';
    const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'conversation.md';
    return { filename, text: await res.text() };
  },
};

export interface ChatBody {
  message?: string;
  conversation_id?: string | null;
  regenerate?: boolean;
  attachments?: { id: string; name: string }[];
  mode?: ChatMode;
}

/**
 * POST /api/chat/stream and yield parsed Server-Sent Events.
 * Aborting the signal closes the connection, which stops generation server-side.
 */
export async function* streamChat(body: ChatBody, signal: AbortSignal): AsyncGenerator<StreamEvent> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/chat/stream`, {
      method: 'POST',
      headers: headers({ 'Content-Type': 'application/json', Accept: 'text/event-stream' }),
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === 'AbortError') return;
    throw new ApiError("Can't reach the server. Is the backend running?", 0, 'NETWORK');
  }
  if (!res.ok) throw await toError(res);
  if (!res.body) throw new ApiError('The server sent an empty response.', 500);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary: number;
      // Events are separated by a blank line.
      while ((boundary = buffer.search(/\r?\n\r?\n/)) !== -1) {
        const raw = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary).replace(/^\r?\n\r?\n/, '');
        const data = raw
          .split(/\r?\n/)
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).replace(/^ /, ''))
          .join('\n');
        if (!data) continue; // comments / heartbeats / retry hints
        try {
          yield JSON.parse(data) as StreamEvent;
        } catch {
          console.warn('Skipping malformed event', data.slice(0, 120));
        }
      }
    }
  } catch (err) {
    if ((err as Error).name === 'AbortError') return;
    throw new ApiError('The connection dropped before the answer finished.', 0, 'STREAM_INTERRUPTED');
  } finally {
    reader.releaseLock();
  }
}
