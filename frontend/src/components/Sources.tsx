import { useState } from 'react';
import { FileText, Globe } from 'lucide-react';
import type { Source } from '@/lib/types';
import { hostname } from '@/lib/utils';

const LIMIT = 5;

export function Sources({ items }: { items: Source[] }) {
  const [all, setAll] = useState(false);
  if (!items.length) return null;
  const shown = all ? items : items.slice(0, LIMIT);

  return (
    <div className="mt-4">
      <p className="mb-2 text-[12.5px] font-semibold text-muted">Sources</p>
      <ul className="flex flex-wrap gap-2">
        {shown.map((s, i) => {
          const label = s.kind === 'doc' ? `${s.title}${s.page ? `, p. ${s.page}` : ''}` : s.title || hostname(s.url);
          const body = (
            <>
              {s.kind === 'doc' ? (
                <span className="flex size-[18px] shrink-0 items-center justify-center rounded bg-sunk font-mono text-[10.5px] text-route-docs">
                  {s.index ?? i + 1}
                </span>
              ) : (
                <Globe className="size-3.5 shrink-0 text-route-agent" />
              )}
              <span className="min-w-0 truncate">{label}</span>
              {s.kind === 'web' && s.url ? <span className="shrink-0 text-faint">{hostname(s.url)}</span> : null}
              {s.kind === 'doc' && !s.index ? <FileText className="size-3.5 shrink-0 text-faint" /> : null}
            </>
          );
          return (
            <li key={`${s.url ?? s.title}-${i}`} className="max-w-full">
              {s.url ? (
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={s.snippet ?? s.title}
                  className="flex max-w-[22rem] items-center gap-2 rounded-lg border border-line bg-raised/70 px-2.5 py-1.5 text-[13px] text-ink transition-colors hover:border-line-strong"
                >
                  {body}
                </a>
              ) : (
                <span title={s.snippet ?? s.title} className="flex max-w-[22rem] items-center gap-2 rounded-lg border border-line bg-raised/70 px-2.5 py-1.5 text-[13px] text-ink">
                  {body}
                </span>
              )}
            </li>
          );
        })}
        {items.length > LIMIT && (
          <li>
            <button
              type="button"
              onClick={() => setAll((a) => !a)}
              className="rounded-lg px-2.5 py-1.5 text-[13px] text-muted hover:text-ink"
            >
              {all ? 'Show fewer' : `Show ${items.length - LIMIT} more`}
            </button>
          </li>
        )}
      </ul>
    </div>
  );
}
