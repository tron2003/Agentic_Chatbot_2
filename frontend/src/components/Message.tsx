import { memo, useState } from 'react';
import { Brain, Check, Copy, FileDown, Loader2, Paperclip, RotateCcw, Telescope } from 'lucide-react';
import { ApprovalCard, ApprovalLog } from './ApprovalCard';
import { LiveActivity } from './LiveActivity';
import { Markdown } from './Markdown';
import { Sources } from './Sources';
import { Timeline } from './Timeline';
import { useChat } from '@/lib/chat-store';
import { ROUTE_LABEL, type Route, type UIMessage } from '@/lib/types';
import { cn, formatDuration } from '@/lib/utils';

export const ROUTE_VAR: Record<Route, string> = { chat: 'var(--route-chat)', rag: 'var(--route-docs)', agent: 'var(--route-agent)' };

/**
 * The station at the top of an answer: a ring in the route's colour and its name.
 * The route's line runs down from it along the whole answer.
 */
function Station({ route, reason, pending, waiting }: { route?: Route; reason?: string; pending: boolean; waiting: boolean }) {
  const color = waiting ? 'var(--signal)' : route ? ROUTE_VAR[route] : 'var(--line-strong)';
  return (
    <div className="relative mb-2.5 flex items-center gap-2.5" title={reason}>
      <span className="relative z-10 -ml-6 flex size-[17px] items-center justify-center rounded-full bg-bg">
        <span
          className={cn('size-[13px] rounded-full border-[3px]', !route && pending && 'animate-pulse')}
          style={{ borderColor: color, background: route ? 'var(--bg)' : 'transparent' }}
        />
      </span>
      <span className="text-[13px] font-semibold" style={{ color: route || waiting ? color : 'var(--text-muted)' }}>
        {waiting ? 'Stopped for your OK' : route ? ROUTE_LABEL[route] : pending ? 'Choosing a route' : 'Answer'}
      </span>
      {reason && route && !pending ? <span className="hidden min-w-0 truncate text-[12.5px] text-faint sm:inline">{reason}</span> : null}
    </div>
  );
}

function UserMessage({ message }: { message: UIMessage }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] sm:max-w-[78%]">
        <div className="rounded-[20px] rounded-br-md bg-ink px-4 py-2.5 text-[15.5px] leading-relaxed text-bg">
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
  const waiting = !!message.pendingApproval?.length && !live;
  // A Deep research report (has a finished writer step) gets an Export PDF button.
  const isReport = !empty && message.steps.some((s) => s.id === 'research-write' && s.status !== 'running') && !message.id.startsWith('pending');
  const memorySaved = message.steps.find((s) => s.id === 'memory-save' && s.status === 'done');
  const line = waiting ? 'var(--signal)' : message.route ? ROUTE_VAR[message.route] : 'var(--line)';

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
    <article className="group/msg relative pl-6" aria-busy={live}>
      {/* the route's line, from the station down the whole answer */}
      <span
        aria-hidden
        className="absolute bottom-1 left-[8px] top-[18px] w-[2px] rounded-full transition-colors duration-500"
        style={{ background: `linear-gradient(to bottom, ${line}, color-mix(in oklab, ${line} 25%, transparent))` }}
      />
      <Station route={message.route} reason={message.routeReason} pending={live} waiting={waiting} />

      <Timeline steps={message.steps} route={message.route} live={live} elapsedMs={message.elapsedMs} />

      {!empty ? (
        <Markdown text={message.content} streaming={live} />
      ) : live ? (
        <LiveActivity steps={message.steps} route={message.route} />
      ) : null}

      {waiting && <ApprovalCard messageId={message.id} actions={message.pendingApproval!} />}

      {message.approvals?.length && !waiting ? <ApprovalLog items={message.approvals} /> : null}

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

      {!live && !waiting && (
        <div className="mt-3 flex flex-wrap items-center gap-1 text-faint transition-opacity sm:opacity-70 sm:group-hover/msg:opacity-100 sm:group-focus-within/msg:opacity-100">
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
          {message.elapsedMs ? (
            <span className="ml-2 text-[12px]">
              {formatDuration(message.elapsedMs)}
              {message.model ? ` with ${message.model}` : ''}
            </span>
          ) : null}
        </div>
      )}
    </article>
  );
}

export const Message = memo(function Message(props: { message: UIMessage; isLast: boolean; onRegenerate: () => void; busy: boolean }) {
  return props.message.role === 'user' ? <UserMessage message={props.message} /> : <AssistantMessage {...props} />;
});
