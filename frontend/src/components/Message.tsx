import { memo, useState } from 'react';
import { Brain, Check, Copy, FileDown, Loader2, Paperclip, RotateCcw, Telescope } from 'lucide-react';
import { LiveActivity } from './LiveActivity';
import { Markdown } from './Markdown';
import { Sources } from './Sources';
import { Timeline } from './Timeline';
import { useChat } from '@/lib/chat-store';
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
        {message.mode === 'deep_research' && (
          <p className="mt-1.5 flex items-center justify-end gap-1 text-[12px] font-medium text-route-agent">
            <Telescope className="size-3" /> Deep research
          </p>
        )}
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
  const [exporting, setExporting] = useState(false);
  const { setMemoryPanelOpen, exportPdf } = useChat();
  const live = message.status === 'streaming';
  const empty = !message.content.trim();
  // A Deep research report (has a finished writer step) gets an Export PDF button.
  const isReport = !empty && message.steps.some((s) => s.id === 'research-write' && s.status !== 'running') && !message.id.startsWith('pending');
  const memorySaved = message.steps.find((s) => s.id === 'memory-save' && s.status === 'done');

  const exportReport = async () => {
    setExporting(true);
    await exportPdf(message.id);
    setExporting(false);
  };

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
        <LiveActivity steps={message.steps} route={message.route} />
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

      {memorySaved && !live && (
        <button
          type="button"
          onClick={() => setMemoryPanelOpen(true)}
          title={memorySaved.detail || 'Open memory'}
          className="activity-in mt-3 inline-flex items-center gap-1.5 rounded-full border border-line bg-raised/70 px-2.5 py-1 text-[12.5px] text-muted transition-colors hover:border-line-strong hover:text-ink"
        >
          <Brain className="size-3.5 text-accent" />
          Memory updated
        </button>
      )}

      {!live && (
        <div
          className={cn(
            'mt-3 flex flex-wrap items-center gap-1 text-faint transition-opacity',
            isReport ? 'opacity-100' : 'opacity-100 sm:opacity-0 sm:group-hover/msg:opacity-100 sm:group-focus-within/msg:opacity-100',
          )}
        >
          {isReport && (
            <button
              type="button"
              onClick={exportReport}
              disabled={exporting}
              className="mr-1 inline-flex items-center gap-1.5 rounded-lg border border-route-agent/40 bg-route-agent/10 px-2.5 py-1 text-[12.5px] font-semibold text-route-agent transition-colors hover:bg-route-agent/15 disabled:opacity-60"
              aria-label="Export this report as a PDF"
            >
              {exporting ? <Loader2 className="size-3.5 animate-spin" /> : <FileDown className="size-3.5" />}
              {exporting ? 'Creating PDF…' : 'Export PDF'}
            </button>
          )}
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
