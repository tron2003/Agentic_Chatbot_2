import type { Route, Step } from './types';
import { hostname } from './utils';

export interface Activity {
  /** Phrases shown one after another, each typed out: "Searching “nvidia price”…", "Reading reuters.com…". */
  phrases: string[];
  /** Sites being read right now, shown as small badges. */
  sites: string[];
}

const quote = (s: string, max = 60) => {
  const t = s.replace(/\s+/g, ' ').trim();
  return `“${t.length > max ? `${t.slice(0, max - 1)}…` : t}”`;
};

function sitesOf(steps: Step[]): string[] {
  const seen = new Set<string>();
  for (const s of steps) {
    for (const it of s.items ?? []) {
      const host = it.url ? hostname(it.url) : '';
      if (host) seen.add(host);
    }
  }
  return [...seen];
}

/**
 * What to say while an answer is being prepared, from the reasoning steps so far.
 * Runs on every step update, so it must stay cheap and pure.
 */
export function describeActivity(steps: Step[], route?: Route): Activity {
  const visible = steps.filter((s) => s.kind !== 'route' && s.kind !== 'memory');
  const running = visible.filter((s) => s.status === 'running');
  const done = visible.filter((s) => s.status !== 'running' && s.status !== 'waiting');

  if (visible.some((s) => s.status === 'waiting') && !running.length) {
    return { phrases: ['Waiting for your approval…'], sites: [] };
  }

  if (running.some((s) => s.id === 'research-write')) {
    const sites = sitesOf(done).slice(0, 6);
    return { phrases: ['Writing the report…', 'Weaving the sources together…', 'Adding citations…'], sites };
  }
  if (running.some((s) => s.id === 'research-plan')) {
    return { phrases: ['Planning the research…', 'Breaking the question into parts…'], sites: [] };
  }
  if (running.some((s) => s.id === 'research-review')) {
    return { phrases: ['Checking what’s missing…', 'Looking for gaps in the sources…'], sites: sitesOf(done).slice(0, 6) };
  }

  const searching = running.filter((s) => s.kind === 'tool');
  if (searching.length) {
    const phrases = searching.map((s) => {
      if (s.tool === 'query_spreadsheet') return 'Crunching the numbers…';
      if (s.tool === 'describe_spreadsheets') return 'Opening your spreadsheets…';
      if (s.tool === 'web_search' || s.id.startsWith('research-')) {
        return s.detail ? `Searching ${quote(s.detail)}…` : 'Searching the web…';
      }
      return `${s.title}…`;
    });
    return { phrases, sites: sitesOf(done).slice(0, 6) };
  }
  if (running.some((s) => s.kind === 'retrieval')) {
    return { phrases: ['Searching your documents…'], sites: [] };
  }

  const sites = sitesOf(done);
  if (sites.length) {
    return {
      phrases: [...sites.slice(0, 5).map((h) => `Reading ${h}…`), 'Putting the answer together…'],
      sites: sites.slice(0, 6),
    };
  }
  if (done.some((s) => s.tool === 'query_spreadsheet')) return { phrases: ['Reading the numbers…', 'Writing it up…'], sites: [] };
  if (done.some((s) => s.kind === 'retrieval')) return { phrases: ['Reading the passages…', 'Writing the answer…'], sites: [] };

  if (route === 'rag') return { phrases: ['Searching your documents…'], sites: [] };
  if (route === 'agent') return { phrases: ['Working out what to look up…'], sites: [] };
  if (route === 'chat') return { phrases: ['Thinking…'], sites: [] };
  return { phrases: ['Reading your message…', 'Choosing a route…'], sites: [] };
}
