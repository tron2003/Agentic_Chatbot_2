import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import type { StoredMessage, UIMessage } from './types';

/** Shown until /api/meta answers with the server's APP_NAME. */
export const APP_NAME_FALLBACK = 'Reittiä';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function uid(prefix = 'tmp'): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}`;
}

export function fromStored(m: StoredMessage): UIMessage {
  const meta = m.metadata ?? {};
  return {
    id: m.id,
    role: m.role,
    content: m.content,
    createdAt: m.created_at,
    route: meta.route,
    routeReason: meta.route_reason,
    steps: meta.steps ?? [],
    sources: meta.sources ?? [],
    attachments: meta.attachments,
    mode: meta.mode,
    status: meta.stopped ? 'stopped' : meta.failed ? 'error' : 'done',
    elapsedMs: meta.elapsed_ms,
    model: meta.model,
    pendingApproval: meta.pending_approval?.actions?.length ? meta.pending_approval.actions : undefined,
    approvals: meta.approvals?.length ? meta.approvals : undefined,
  };
}

/** The greeting for the time of day, in the reader's own clock. */
export function greeting(now = new Date()): string {
  const h = now.getHours();
  if (h < 5) return 'Up late';
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

/**
 * The user's first name from long-term memory ("Name is Kanish", "Goes by Kanish",
 * "User's name is Kanish"), or null.
 */
export function nameFromMemories(items: { content: string }[]): string | null {
  for (const { content } of items) {
    const m = /\b(?:[Nn]ame is|[Gg]oes by|[Cc]alled|[Cc]all me|I am|I'm)\s+(\p{Lu}[\p{L}'-]{1,30})/u.exec(content);
    if (m) return m[1];
  }
  // Facts are often written about the user in the third person: "Kanish is an engineer who…".
  for (const { content } of items) {
    const m = /^(\p{Lu}[\p{L}'-]{1,30}) (?:is|prefers|builds|works|uses|likes|wants|lives|has)\b/u.exec(content.trim());
    if (m && !NOT_NAMES.has(m[1].toLowerCase())) return m[1];
  }
  return null;
}

const NOT_NAMES = new Set(['user', 'the', 'they', 'he', 'she', 'it', 'this', 'that', 'my', 'their', 'his', 'her', 'python', 'langgraph']);

/** "11:42" today, "Yesterday", or "Mon 24 Nov" — the time column of the home board. */
export function boardTime(iso: string, now = new Date()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const group = dateGroup(iso, now);
  if (group === 'Today') return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  if (group === 'Yesterday') return 'Yesterday';
  return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDuration(ms?: number): string {
  if (!ms && ms !== 0) return '';
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)} s`;
}

export function hostname(url?: string | null): string {
  if (!url) return '';
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

export type DateGroup = 'Today' | 'Yesterday' | 'Previous 7 days' | 'Previous 30 days' | 'Older';

export function dateGroup(iso: string, now = new Date()): DateGroup {
  const d = new Date(iso);
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const day = 86_400_000;
  const t = d.getTime();
  if (t >= startOfToday) return 'Today';
  if (t >= startOfToday - day) return 'Yesterday';
  if (t >= startOfToday - 7 * day) return 'Previous 7 days';
  if (t >= startOfToday - 30 * day) return 'Previous 30 days';
  return 'Older';
}

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}
