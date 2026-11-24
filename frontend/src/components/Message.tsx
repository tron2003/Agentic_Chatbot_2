import { memo, useState } from 'react';
import { Check, Copy, Paperclip, RotateCcw } from 'lucide-react';
import { Markdown } from './Markdown';
import { Sources } from './Sources';
import { Timeline } from './Timeline';
import { ROUTE_LABEL, type Route, type UIMessage } from '@/lib/types';
import { cn, formatDuration } from '@/lib/utils';

const ROUTE_CLASS: Record<Route, string> = {
  chat: 'text-route-chat',
  rag: 'text-route-docs',
  agent: 'text-route-agent',
};

function RouteMarker({ route, reason, pending }: { route?: Route; reason?: string; pending: boolean }) {
  if (!route) {
    return (
      <span className="inline-flex items-center gap-2 text-[13px] text-muted">
        <span className="size-2 animate-pulse rounded-full bg-line-strong" />
        {pending ? 'Choosing a route' : 'Answer'}
      </span>
    );
  }
  return (
    <span className={cn('inline-flex items-center gap-2 text-[13px] font-semibold', ROUTE_CLASS[route])} title={reason}>
      <span className="size-2.5 rounded-full border-2 border-current" />
      {ROUTE_LABEL[route]}
    </span>
  );
}

function UserMessage({ message }: { message: UIMessage }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] sm:max-w-[75%]">
        <div className="rounded-2xl rounded-br-md border border-line bg-raised px-4 py-2.5 text-[15px] leading-relaxed text-ink shadow-lift">
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        </div>
        {message.attachments?.length ? (
          <ul className="mt-1.5 flex flex-wrap justify-end gap-1.5">
            {message.attachments.map((a) => (
              <li key={a.id} className="inline-flex items-center gap-1 rounded-md bg-sunk px-2 py-0.5 text-[12px] text-muted">
                <Paperclip className="size-3" />
                {a.name}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

function AssistantMessage({ message, isLast, onRegenerate, busy }: { message: UIMessage; isLast: boolean; onRegenerate: () => void; busy: boolean }) {
  const [copied, setCopied] = useState(false);
  const live = message.status === 'streaming';
  const empty = !message.content.trim();

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked */
    }
  };

  return (
    <article className="group/msg" aria-busy={live}>
      <div className="mb-2 flex items-center gap-3">
        <RouteMarker route={message.route} reason={message.routeReason} pending={live} />
      </div>

      <Timeline steps={message.steps} route={message.route} live={live} elapsedMs={message.elapsedMs} />

      {!empty ? (
        <Markdown text={message.content} streaming={live} />
      ) : live ? (
        <div className="space-y-2 py-1" aria-label="Writing the answer">
          <div className="h-3 w-3/4 animate-pulse rounded bg-sunk" />
          <div className="h-3 w-1/2 animate-pulse rounded bg-sunk" />
        </div>
      ) : null}

      {message.status === 'error' && (
        <div role="alert" className="mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-danger/40 bg-danger/10 px-3.5 py-2.5 text-[14px] text-ink">
          <span className="min-w-0 flex-1">{message.error || 'The answer could not be completed.'}</span>
          {isLast && (
            <button type="button" onClick={onRegenerate} disabled={busy} className="rounded-lg border border-line bg-raised px-3 py-1 text-[13px] font-semibold hover:border-line-strong disabled:opacity-50">
              Try again
            </button>
          )}
        </div>
      )}

      {message.status === 'stopped' && <p className="mt-2 text-[13px] text-faint">Stopped before the answer finished.</p>}

      <Sources items={message.sources} />

      {!live && (
        <div className="mt-3 flex items-center gap-1 text-faint opacity-100 transition-opacity sm:opacity-0 sm:group-hover/msg:opacity-100 sm:group-focus-within/msg:opacity-100">
          {!empty && (
            <button type="button" onClick={copy} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[12.5px] hover:bg-raised hover:text-ink" aria-label="Copy answer">
              {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          )}
          {isLast && (
            <button type="button" onClick={onRegenerate} disabled={busy} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[12.5px] hover:bg-raised hover:text-ink disabled:opacity-40" aria-label="Regenerate answer">
              <RotateCcw className="size-3.5" />
              Regenerate
            </button>
          )}
          {message.elapsedMs ? <span className="ml-2 text-[12px]">{formatDuration(message.elapsedMs)}{message.model ? `, ${message.model}` : ''}</span> : null}
        </div>
      )}
    </article>
  );
}

export const Message = memo(function Message(props: { message: UIMessage; isLast: boolean; onRegenerate: () => void; busy: boolean }) {
  return props.message.role === 'user' ? <UserMessage message={props.message} /> : <AssistantMessage {...props} />;
});
