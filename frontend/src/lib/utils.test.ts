import { describe, expect, it } from 'vitest';
import type { StoredMessage } from './types';
import { dateGroup, formatBytes, formatDuration, fromStored, hostname } from './utils';

describe('fromStored', () => {
  const base: StoredMessage = {
    id: 'm1',
    conversation_id: 'c1',
    role: 'assistant',
    content: 'Answer',
    created_at: '2026-10-16T04:00:00Z',
    metadata: {
      route: 'agent',
      route_reason: 'Needs a tool',
      steps: [{ id: 's1', kind: 'tool', title: 'Calculating', status: 'done', ts: '2026-10-16T04:00:00Z' }],
      sources: [{ kind: 'web', title: 'Docs', url: 'https://example.com' }],
      elapsed_ms: 1200,
      model: 'demo',
    },
  };

  it('maps stored metadata onto the UI message', () => {
    const m = fromStored(base);
    expect(m).toMatchObject({ route: 'agent', routeReason: 'Needs a tool', status: 'done', elapsedMs: 1200, model: 'demo' });
    expect(m.steps).toHaveLength(1);
    expect(m.sources[0].url).toBe('https://example.com');
  });

  it('keeps stopped and failed answers visible as such', () => {
    expect(fromStored({ ...base, metadata: { stopped: true } }).status).toBe('stopped');
    expect(fromStored({ ...base, metadata: { failed: true } }).status).toBe('error');
    expect(fromStored({ ...base, metadata: {} }).steps).toEqual([]);
  });
});

describe('dateGroup', () => {
  const now = new Date(2026, 9, 16, 12, 0, 0);
  it.each([
    [new Date(2026, 9, 16, 1, 0), 'Today'],
    [new Date(2026, 9, 15, 23, 0), 'Yesterday'],
    [new Date(2026, 9, 11, 9, 0), 'Previous 7 days'],
    [new Date(2026, 8, 30, 9, 0), 'Previous 30 days'],
    [new Date(2026, 5, 1, 9, 0), 'Older'],
  ])('%s is %s', (date, group) => {
    expect(dateGroup(date.toISOString(), now)).toBe(group);
  });
});

describe('formatting', () => {
  it('formats sizes, durations and hosts', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2 KB');
    expect(formatBytes(3.5 * 1024 * 1024)).toBe('3.5 MB');
    expect(formatDuration(450)).toBe('450 ms');
    expect(formatDuration(2400)).toBe('2.4 s');
    expect(formatDuration(42_000)).toBe('42 s');
    expect(formatDuration(undefined)).toBe('');
    expect(hostname('https://www.example.com/a/b')).toBe('example.com');
    expect(hostname('not a url')).toBe('not a url');
  });
});
