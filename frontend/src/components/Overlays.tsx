import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { KeyRound, X } from 'lucide-react';
import { useChat } from '@/lib/chat-store';
import { cn } from '@/lib/utils';

export function Toasts() {
  const { toasts, dismissToast } = useChat();
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-28 z-[60] flex flex-col items-center gap-2 px-4" role="status" aria-live="polite">
      <AnimatePresence initial={false}>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            layout
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6 }}
            className={cn(
              'glass pointer-events-auto flex max-w-[30rem] items-start gap-3 rounded-xl border px-3.5 py-2.5 text-[14px] shadow-lift',
              t.kind === 'error' ? 'border-danger/50 text-ink' : 'border-line text-ink',
            )}
          >
            <span className={cn('mt-[7px] size-2 shrink-0 rounded-full', t.kind === 'error' ? 'bg-danger' : t.kind === 'success' ? 'bg-route-agent' : 'bg-route-chat')} />
            <span className="min-w-0 flex-1">{t.text}</span>
            <button type="button" onClick={() => dismissToast(t.id)} className="rounded p-0.5 text-faint hover:text-ink" aria-label="Dismiss">
              <X className="size-3.5" />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

export function ApiKeyDialog() {
  const { needsApiKey, submitApiKey } = useChat();
  const [value, setValue] = useState('');
  if (!needsApiKey) return null;
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="key-title"
        onSubmit={(e) => {
          e.preventDefault();
          void submitApiKey(value);
        }}
        className="w-full max-w-[400px] rounded-2xl border border-line bg-bg p-5 shadow-lift"
      >
        <KeyRound className="size-6 text-route-chat" />
        <h2 id="key-title" className="mt-3 text-[18px] font-[780] text-ink">
          Enter the access key
        </h2>
        <p className="mt-1 text-[14px] leading-relaxed text-muted">This deployment requires a key. It's saved in this browser only.</p>
        <input
          type="password"
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Access key"
          autoComplete="current-password"
          className="mt-4 w-full rounded-xl border border-line bg-raised px-3 py-2.5 text-[15px] text-ink outline-none focus:border-line-strong"
        />
        <button type="submit" disabled={!value.trim()} className="mt-4 w-full rounded-xl bg-accent py-2.5 text-[14.5px] font-semibold text-accent-ink disabled:opacity-40">
          Unlock
        </button>
      </form>
    </div>
  );
}

export function SetupBanner() {
  const { meta, serverDown } = useChat();
  if (serverDown) {
    return (
      <div className="glass mx-auto mt-16 w-fit max-w-[calc(100%-2rem)] rounded-xl border border-danger/50 px-4 py-2 text-center text-[13.5px] text-ink">
        Can't reach the server. Start the backend with <code className="font-mono text-[12.5px]">python run.py</code>; this page reconnects on its own.
      </div>
    );
  }
  if (meta && !meta.llm_ready) {
    return (
      <div className="glass mx-auto mt-16 w-fit max-w-[calc(100%-2rem)] rounded-xl border border-route-docs/60 px-4 py-2 text-center text-[13.5px] text-ink">
        {meta.llm_error ?? 'No language model is configured.'}
      </div>
    );
  }
  return null;
}
