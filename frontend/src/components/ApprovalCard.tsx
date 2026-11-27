import { useState } from 'react';
import { Check, ChevronDown, Hand, Loader2, X } from 'lucide-react';
import { useChat, type Decision } from '@/lib/chat-store';
import type { ApprovalRecord, PendingAction } from '@/lib/types';
import { APP_NAME_FALLBACK, cn } from '@/lib/utils';

export function serverLabel(server?: string): string {
  if (!server) return '';
  if (server === 'agents') return 'External agent';
  if (server === 'builtin') return 'Built in';
  return server;
}

function valueText(value: unknown): string {
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** The arguments the agent wants to send, as a readable list. Long values fold. */
function Args({ args }: { args: Record<string, unknown> }) {
  const entries = Object.entries(args ?? {});
  const [open, setOpen] = useState(false);
  if (!entries.length) return <p className="text-[13px] text-faint">No details sent with this action.</p>;
  const long = entries.some(([, v]) => valueText(v).length > 220 || valueText(v).split('\n').length > 6);
  return (
    <div>
      <dl className={cn('grid grid-cols-[minmax(0,auto)_1fr] gap-x-3 gap-y-1.5', long && !open && 'max-h-[9.5rem] overflow-hidden [mask-image:linear-gradient(to_bottom,black_70%,transparent)]')}>
        {entries.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="pt-px font-mono text-[12px] text-faint">{k}</dt>
            <dd className="min-w-0 whitespace-pre-wrap break-words text-[13.5px] leading-snug text-ink">{valueText(v)}</dd>
          </div>
        ))}
      </dl>
      {long && (
        <button type="button" onClick={() => setOpen((o) => !o)} className="mt-1 inline-flex items-center gap-1 text-[12.5px] text-muted hover:text-ink">
          <ChevronDown className={cn('size-3.5 transition-transform', open && 'rotate-180')} />
          {open ? 'Show less' : 'Show everything it will send'}
        </button>
      )}
    </div>
  );
}

/**
 * The agent stopped before an action (sending, creating, deleting, writing, asking
 * another agent). Nothing runs until the user approves; declining tells the agent so.
 */
export function ApprovalCard({ messageId, actions }: { messageId: string; actions: PendingAction[] }) {
  const { approve, streaming, meta } = useChat();
  const [chosen, setChosen] = useState<Record<string, boolean>>(() => Object.fromEntries(actions.map((a) => [a.id, true])));
  const [always, setAlways] = useState<Record<string, boolean>>({});
  const [sending, setSending] = useState<Decision | null>(null);
  const app = meta?.app_name ?? APP_NAME_FALLBACK;
  const several = actions.length > 1;
  const picked = actions.filter((a) => chosen[a.id]);

  const decide = async (mode: 'chosen' | 'decline') => {
    const decisions: Record<string, Decision> = Object.fromEntries(
      actions.map((a) => [a.id, mode === 'chosen' && chosen[a.id] ? 'approve' : 'decline'] as const),
    );
    const allow = mode === 'chosen' ? actions.filter((a) => chosen[a.id] && always[a.id]).map((a) => a.key) : [];
    setSending(mode === 'decline' ? 'decline' : 'approve');
    await approve(messageId, decisions, allow);
    setSending(null);
  };

  return (
    <section
      aria-label="Waiting for your approval"
      className="activity-in relative mt-1 overflow-hidden rounded-2xl border border-signal/45 bg-raised shadow-lift"
    >
      <div className="hazard-edge h-1.5 w-full opacity-80" aria-hidden />
      <div className="px-4 pb-4 pt-3.5 sm:px-5">
        <div className="flex items-start gap-3">
          <span className="signal-pulse mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-signal text-white">
            <Hand className="size-4" />
          </span>
          <div className="min-w-0">
            <h3 className="text-[16px] font-[760] leading-tight tracking-[-0.01em] text-ink">
              {several ? `${actions.length} actions are waiting for your OK` : 'Waiting for your OK'}
            </h3>
            <p className="mt-0.5 text-[13.5px] leading-snug text-muted">
              {app} wants to {several ? 'do these' : 'do this'} for you. Nothing happens until you decide.
            </p>
          </div>
        </div>

        <ul className="mt-3.5 space-y-2.5">
          {actions.map((a) => (
            <li key={a.id} className={cn('rounded-xl border border-line bg-bg/60 px-3.5 py-3', several && !chosen[a.id] && 'opacity-55')}>
              <div className="mb-2 flex flex-wrap items-center gap-x-2.5 gap-y-1">
                {several && (
                  <input
                    type="checkbox"
                    checked={!!chosen[a.id]}
                    onChange={(e) => setChosen((c) => ({ ...c, [a.id]: e.target.checked }))}
                    className="size-4 accent-[var(--signal)]"
                    aria-label={`Run ${a.title}`}
                  />
                )}
                <span className="text-[14.5px] font-semibold text-ink">{a.title}</span>
                <span className="rounded-md bg-sunk px-1.5 py-px font-mono text-[11.5px] text-muted" title={a.description || undefined}>
                  {serverLabel(a.server) ? `${serverLabel(a.server)} / ` : ''}
                  {a.tool}
                </span>
              </div>
              <Args args={a.args} />
              <label className="mt-2.5 inline-flex cursor-pointer items-center gap-2 text-[12.5px] text-muted hover:text-ink">
                <input
                  type="checkbox"
                  checked={!!always[a.id]}
                  onChange={(e) => setAlways((s) => ({ ...s, [a.id]: e.target.checked }))}
                  className="size-3.5 accent-[var(--signal)]"
                />
                Don't ask again for {a.tool}
              </label>
            </li>
          ))}
        </ul>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void decide('chosen')}
            disabled={streaming || !!sending || (several && !picked.length)}
            className="inline-flex items-center gap-1.5 rounded-xl bg-ink px-4 py-2 text-[14px] font-semibold text-bg transition-transform hover:-translate-y-px active:translate-y-0 disabled:opacity-45 disabled:hover:translate-y-0"
          >
            {sending === 'approve' ? <Loader2 className="size-4 animate-spin" /> : <Check className="size-4" />}
            {several ? `Run ${picked.length === actions.length ? 'all' : `${picked.length} of ${actions.length}`}` : 'Approve'}
          </button>
          <button
            type="button"
            onClick={() => void decide('decline')}
            disabled={streaming || !!sending}
            className="inline-flex items-center gap-1.5 rounded-xl border border-line px-4 py-2 text-[14px] font-semibold text-ink hover:border-line-strong disabled:opacity-45"
          >
            {sending === 'decline' ? <Loader2 className="size-4 animate-spin" /> : <X className="size-4" />}
            {several ? 'Decline all' : 'Decline'}
          </button>
          <span className="text-[12.5px] text-faint">Sending a new message also declines.</span>
        </div>
      </div>
    </section>
  );
}

const DECISION_TEXT: Record<ApprovalRecord['decision'], string> = {
  approve: 'You approved',
  decline: 'You declined',
  dropped: 'Not approved',
};

/** What was decided for a paused answer, kept under it afterwards. */
export function ApprovalLog({ items }: { items: ApprovalRecord[] }) {
  return (
    <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Approvals">
      {items.map((a) => (
        <li
          key={`${a.id}-${a.decision}`}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[12.5px]',
            a.decision === 'approve' ? 'border-route-agent/40 text-route-agent' : 'border-line text-muted',
          )}
          title={a.args ? JSON.stringify(a.args) : undefined}
        >
          {a.decision === 'approve' ? <Check className="size-3.5" /> : <X className="size-3.5" />}
          {DECISION_TEXT[a.decision]}: {a.title || a.tool}
        </li>
      ))}
    </ul>
  );
}
