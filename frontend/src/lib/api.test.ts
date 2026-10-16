import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, streamChat } from './api';
import type { StreamEvent } from './types';

function sseResponse(chunks: string[], init: ResponseInit = {}) {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((c) => controller.enqueue(encoder.encode(c)));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { 'content-type': 'text/event-stream' }, ...init });
}

async function collect(gen: AsyncGenerator<StreamEvent>) {
  const out: StreamEvent[] = [];
  for await (const ev of gen) out.push(ev);
  return out;
}

afterEach(() => vi.unstubAllGlobals());

describe('streamChat', () => {
  it('parses events split across network chunks and skips heartbeats', async () => {
    const meta = { type: 'meta', conversation_id: 'c1', message_id: 'm1', user_message_id: 'u1', is_new: true };
    const payload = [
      'retry: 3000\n\n',
      `data: ${JSON.stringify(meta)}\n\n`,
      ': ping\n\n',
      'data: {"type":"tok',
      'en","text":"Hel"}\n',
      '\ndata: {"type":"token","text":"lo"}\r\n\r\n',
      'data: {"type":"draft_reset"}\n\n',
    ];
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse(payload)));

    const events = await collect(streamChat({ message: 'hi' }, new AbortController().signal));
    expect(events.map((e) => e.type)).toEqual(['meta', 'token', 'token', 'draft_reset']);
    expect(events.filter((e) => e.type === 'token').map((e) => (e as { text: string }).text).join('')).toBe('Hello');
  });

  it('surfaces the server error message and request id', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ error: { code: 'HTTP_429', message: 'Too many requests.', request_id: 'r1' } }), {
          status: 429,
          headers: { 'content-type': 'application/json' },
        }),
      ),
    );
    const err = await collect(streamChat({ message: 'hi' }, new AbortController().signal)).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(429);
    expect(err.message).toBe('Too many requests.');
    expect(err.requestId).toBe('r1');
  });

  it('reports an unreachable server as a network error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))));
    const err = await collect(streamChat({ message: 'hi' }, new AbortController().signal)).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe('NETWORK');
  });

  it('ends quietly when the user stops the stream', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Promise.reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))),
    );
    const controller = new AbortController();
    controller.abort();
    await expect(collect(streamChat({ message: 'hi' }, controller.signal))).resolves.toEqual([]);
  });
});

describe('api client', () => {
  it('sends JSON bodies and parses 204 responses', async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(api.remove('c 1')).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith('/api/conversations/c%201', expect.objectContaining({ method: 'DELETE' }));
  });

  it('uses the message from structured errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ error: { code: 'HTTP_404', message: 'Conversation not found.' } }), { status: 404 }),
      ),
    );
    await expect(api.conversation('missing')).rejects.toMatchObject({ status: 404, message: 'Conversation not found.' });
  });
});
