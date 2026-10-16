import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { ChevronDown } from 'lucide-react';
import type { Route, Step } from '@/lib/types';
import { cn, formatDuration } from '@/lib/utils';

const ROUTE_VAR: Record<Route, string> = { chat: 'var(--route-chat)', rag: 'var(--route-docs)', agent: 'var(--route-agent)' };

/**
 * The agent's reasoning drawn as a transit line: each step is a stop.
 * Running stops pulse; finished stops fill in. Expanded while the answer is
 * being produced, collapsed to a one-line summary afterwards.
 */
export function Timeline({ steps, route, live, elapsedMs }: { steps: Step[]; route?: Route; live: boolean; elapsedMs?: number }) {
  const visible = steps.filter((s) => s.kind !== 'route');
  const [open, setOpen] = useState(live);

  useEffect(() => {
    setOpen(live);
  }, [live]);

  if (!visible.length) return null;
  const color = route ? ROUTE_VAR[route] : 'var(--line-strong)';
  const running = visible.find((s) => s.status === 'running');
  const toolCount = visible.filter((s) => s.kind === 'tool').length;
  const summary = live
    ? running?.title ?? 'Working'
    : `${visible.length} ${visible.length === 1 ? 'step' : 'steps'}${toolCount ? `, ${toolCount} ${toolCount === 1 ? 'tool call' : 'tool calls'}` : ''}`;

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
            {visible.map((s, i) => (
              <li key={s.id} className="relative flex gap-3 pb-3 pt-1 last:pb-1">
                {/* line segment */}
                {i < visible.length - 1 && (
                  <span className="absolute left-[5px] top-[18px] bottom-[-4px] w-[2px] -translate-x-1/2 rounded" style={{ background: color, opacity: 0.45 }} />
                )}
                <span className="relative mt-[5px] flex size-[11px] shrink-0 items-center justify-center">
                  {s.status === 'running' && (
                    <span className="absolute inline-flex size-[11px] animate-ping rounded-full opacity-60" style={{ background: color }} />
                  )}
                  <span
                    className="relative size-[11px] rounded-full border-2"
                    style={{
                      borderColor: s.status === 'error' ? 'var(--danger)' : color,
                      background: s.status === 'done' ? color : 'var(--bg)',
                    }}
                  />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[13.5px] font-semibold leading-snug text-ink">{s.title}</p>
                  {s.detail ? (
                    <p className={cn('mt-0.5 text-[13px] leading-snug text-muted', s.kind === 'thinking' ? 'line-clamp-3' : 'line-clamp-2 break-all')}>
                      {s.detail}
                    </p>
                  ) : null}
                  {s.result && s.status !== 'running' ? (
                    <p className={cn('mt-0.5 line-clamp-2 text-[12.5px] leading-snug', s.status === 'error' ? 'text-danger' : 'text-faint')}>
                      {s.result}
                    </p>
                  ) : null}
                </div>
              </li>
            ))}
          </motion.ol>
        )}
      </AnimatePresence>
    </div>
  );
}
