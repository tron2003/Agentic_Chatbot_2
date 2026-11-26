import { useEffect, useMemo, useState } from 'react';
import { describeActivity } from '@/lib/activity';
import type { Route, Step } from '@/lib/types';
import { prefersReducedMotion } from '@/lib/utils';

const TYPE_MS = 22; // per character
const HOLD_MS = 1500; // a finished phrase stays this long before the next one

function hue(text: string): number {
  let h = 0;
  for (const ch of text) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

/** A site as a small lettered badge (no favicon requests, so nothing leaks to a third party). */
export function SiteBadge({ host, delay = 0 }: { host: string; delay?: number }) {
  const h = hue(host);
  return (
    <span
      title={host}
      className="activity-in inline-flex size-[18px] shrink-0 items-center justify-center rounded-full text-[10px] font-bold uppercase text-white ring-2 ring-bg"
      style={{ background: `hsl(${h} 55% 45%)`, animationDelay: `${delay}ms` }}
    >
      {host.replace(/^www\./, '')[0]}
    </span>
  );
}

/**
 * Shown under the route while the answer hasn't started: what is happening right now,
 * typed out phrase by phrase with a light shimmer ("Searching “nvidia price”…",
 * "Reading reuters.com…"), with the sites being read as badges.
 */
export function LiveActivity({ steps, route }: { steps: Step[]; route?: Route }) {
  const { phrases, sites } = useMemo(() => describeActivity(steps, route), [steps, route]);
  const key = phrases.join('\u0001');
  const [index, setIndex] = useState(0);
  const [shown, setShown] = useState(0);
  const reduced = useMemo(prefersReducedMotion, []);

  // New set of phrases: start again from the first.
  useEffect(() => {
    setIndex(0);
    setShown(reduced ? Number.MAX_SAFE_INTEGER : 0);
  }, [key, reduced]);

  const phrase = phrases[Math.min(index, phrases.length - 1)] ?? '';

  useEffect(() => {
    if (reduced) return;
    if (shown < phrase.length) {
      const t = window.setTimeout(() => setShown((n) => n + 1), TYPE_MS);
      return () => window.clearTimeout(t);
    }
    if (phrases.length > 1) {
      const t = window.setTimeout(() => {
        setIndex((i) => (i + 1) % phrases.length);
        setShown(0);
      }, HOLD_MS);
      return () => window.clearTimeout(t);
    }
  }, [shown, phrase, phrases.length, reduced]);

  const typing = shown < phrase.length;
  return (
    <div className="flex min-h-[28px] items-center gap-2.5 py-1" role="status" aria-live="polite" aria-label={phrase}>
      {sites.length > 0 && (
        <span className="flex -space-x-1.5" aria-hidden>
          {sites.map((s, i) => (
            <SiteBadge key={s} host={s} delay={i * 70} />
          ))}
        </span>
      )}
      <span className="min-w-0 truncate text-[14.5px]" aria-hidden>
        <span className={typing ? 'text-muted' : 'shimmer-text'}>{phrase.slice(0, shown)}</span>
        {typing && <span className="typing-caret" />}
      </span>
    </div>
  );
}
