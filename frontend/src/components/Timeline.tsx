import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { ChevronDown } from 'lucide-react';
import { SiteBadge } from './LiveActivity';
import type { Route, Step } from '@/lib/types';
import { cn, formatDuration, hostname } from '@/lib/utils';

/** What a search found, popping in one by one: a lettered badge and the site, linked. */
function FoundItems({ items }: { items: NonNullable<Step['items']> }) {
  return (
    <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label="Found">
      {items.slice(0, 6).map((it, i) => {
        const host = it.url ? hostname(it.url) : '';
        const label = host || it.title;
        const chip = (
          <>
            <SiteBadge host={label || '?'} />
            <span className="max-w-[11rem] truncate">{label}</span>
          </>
        );
        const cls =
          'inline-flex items-center gap-1.5 rounded-full border border-line bg-raised/60 py-0.5 pl-0.5 pr-2 text-[12px] text-muted';
        return (
          <li key={`${it.url ?? it.title}-${i}`} style={{ animationDelay: `${i * 70}ms` }} className="activity-in">
            {it.url ? (
              <a href={it.url} target="_blank" rel="noopener noreferrer" title={it.title} className={cn(cls, 'hover:border-line-strong hover:text-ink')}>
                {chip}
              </a>
            ) : (
              <span title={it.title} className={cls}>
                {chip}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

const ROUTE_VAR: Record<Route, string> = { chat: 'var(--route-chat)', rag: 'var(--route-docs)', agent: 'var(--route-agent)' };

/**
 * The agent's reasoning drawn as a transit line: each step is a stop.
 * Running stops pulse; finished stops fill in. Expanded while the answer is
 * being produced, collapsed to a one-line summary afterwards.
 */
export function Timeline({ steps, route, live, elapsedMs }: { steps: Step[]; route?: Route; live: boolean; elapsedMs?: number }) {
  // Memory work (recall, save, summarise) isn't shown here: saving shows as a small "Memory updated" note under the answer.
  const visible = steps.filter((s) => s.kind !== 'route' && s.kind !== 'memory');
  const [open, setOpen] = useState(live);

  useEffect(() => {
    setOpen(live);
  }, [live]);

  if (!visible.length) return null;
  const color = route ? ROUTE_VAR[route] : 'var(--line-strong)';
  const running = visible.find((s) => s.status === 'running');
  const toolCount = visible.filter((s) => s.kind === 'tool').length;
  const searches = visible.filter((s) => s.id.startsWith('research-') && s.kind === 'tool').length;
  const tools = searches
    ? `, ${searches} ${searches === 1 ? 'search' : 'searches'}`
    : toolCount
      ? `, ${toolCount} ${toolCount === 1 ? 'tool call' : 'tool calls'}`
      : '';
  const summary = live ? running?.title ?? 'Working' : `${visible.length} ${visible.length === 1 ? 'step' : 'steps'}${tools}`;

  return (
    <div className="mb-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="group inline-flex items-center gap-2 rounded-lg py-1 pr-2 text-[13px] text-muted hover:text-ink"
      >
        <span className="relative flex size-3 items-center justify-center">
          {live && <span className="absolute inline-flex size-3 animate-ping rounded-full opacity-50" style={{ background: color }} />}
          <span className="relative size-2 rounded-full" style={{ background: color }} />
        </span>
        <span className={cn(live && 'text-ink')}>{summary}</span>
        {!live && elapsedMs ? <span className="text-faint">in {formatDuration(elapsedMs)}</span> : null}
        <ChevronDown className={cn('size-3.5 transition-transform', open && 'rotate-180')} />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.ol
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className="relative overflow-hidden pl-[5px]"
          >
            {visible.map((s, i) => {
              const dot = color;
              return (
              <li key={s.id} className="relative flex gap-3 pb-3 pt-1 last:pb-1">
                {/* line segment */}
                {i < visible.length - 1 && (
                  <span className="absolute left-[5px] top-[18px] bottom-[-4px] w-[2px] -translate-x-1/2 rounded" style={{ background: color, opacity: 0.45 }} />
                )}
                <span className="relative mt-[5px] flex size-[11px] shrink-0 items-center justify-center">
                  {s.status === 'running' && (
                    <span className="absolute inline-flex size-[11px] animate-ping rounded-full opacity-60" style={{ background: dot }} />
                  )}
                  <span
                    className="relative size-[11px] rounded-full border-2"
                    style={{
                      borderColor: s.status === 'error' ? 'var(--danger)' : dot,
                      background: s.status === 'done' ? dot : 'var(--bg)',
                    }}
                  />
                </span>
                <div className="min-w-0 flex-1">
                  <p className={cn('text-[13.5px] font-semibold leading-snug', s.status === 'running' ? 'shimmer-text' : 'text-ink')}>
                    {s.title}
                  </p>
                  {s.detail ? (
                    <p
                      className={cn(
                        'mt-0.5 text-[13px] leading-snug text-muted',
                        s.kind === 'thinking' || s.kind === 'memory' ? 'line-clamp-6 whitespace-pre-line' : 'line-clamp-2 break-all',
                      )}
                    >
                      {s.detail}
                    </p>
                  ) : null}
                  {s.result && s.status !== 'running' ? (
                    <p className={cn('mt-0.5 line-clamp-2 text-[12.5px] leading-snug', s.status === 'error' ? 'text-danger' : 'text-faint')}>
                      {s.result}
                    </p>
                  ) : null}
                  {s.items?.length && s.status !== 'running' ? <FoundItems items={s.items} /> : null}
                </div>
              </li>
              );
            })}
          </motion.ol>
        )}
      </AnimatePresence>
    </div>
  );
}
