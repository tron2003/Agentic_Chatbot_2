import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Brain, Database, Loader2, Plus, Trash2, X } from 'lucide-react';
import { api, ApiError } from '@/lib/api';
import { useChat } from '@/lib/chat-store';
import type { MemoryList } from '@/lib/types';
import { APP_NAME_FALLBACK, cn } from '@/lib/utils';

function when(iso?: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

/**
 * Long-term memory: what the assistant remembers about the user across every
 * conversation. Facts are saved by the remember block after an answer, or added
 * here by hand; each one can be deleted.
 */
export function MemoryPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { toast, meta } = useChat();
  const [data, setData] = useState<MemoryList | null>(null);
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const app = meta?.app_name ?? APP_NAME_FALLBACK;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.memories());
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Couldn't load memories.", 'error');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (open) {
      void load();
      closeRef.current?.focus();
    } else {
      setConfirmClear(false);
    }
  }, [open, load]);

  const add = async (e: FormEvent) => {
    e.preventDefault();
    const content = draft.trim();
    if (content.length < 2) return;
    setSaving(true);
    try {
      const item = await api.addMemory(content);
      setData((d) => (d ? { ...d, items: [item, ...d.items.filter((m) => m.id !== item.id)] } : d));
      setDraft('');
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Couldn't save that.", 'error');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: string) => {
    const prev = data;
    setData((d) => (d ? { ...d, items: d.items.filter((m) => m.id !== id) } : d));
    try {
      await api.removeMemory(id);
    } catch (err) {
      setData(prev);
      toast(err instanceof ApiError ? err.message : "Couldn't delete that memory.", 'error');
    }
  };

  const clearAll = async () => {
    try {
      const { deleted } = await api.clearMemories();
      setData((d) => (d ? { ...d, items: [] } : d));
      toast(`Forgot ${deleted} ${deleted === 1 ? 'memory' : 'memories'}.`, 'success');
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Couldn't clear memory.", 'error');
    } finally {
      setConfirmClear(false);
    }
  };

  const items = data?.items ?? [];
  const persistent = data?.backend === 'postgres';

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="scrim"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px]"
            onClick={onClose}
          />
          <motion.aside
            key="panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="memory-title"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 380, damping: 38 }}
            onKeyDown={(e) => e.key === 'Escape' && onClose()}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[420px] flex-col border-l border-line bg-bg shadow-lift"
          >
            <div className="flex items-start justify-between gap-4 px-5 pb-2 pt-5">
              <div>
                <h2 id="memory-title" className="flex items-center gap-2 text-[19px] font-[780] tracking-[-0.01em] text-ink">
                  <Brain className="size-5 text-accent" /> Memory
                </h2>
                <p className="mt-1 text-[14px] leading-relaxed text-muted">
                  What {app} remembers about you across conversations. It saves facts you share, like your name, projects and
                  preferences, and uses them in every chat.
                </p>
              </div>
              <button ref={closeRef} type="button" onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-raised hover:text-ink" aria-label="Close memory">
                <X className="size-4" />
              </button>
            </div>

            <div className="px-5 pt-2">
              <p
                className={cn(
                  'flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12.5px]',
                  persistent ? 'bg-route-agent/10 text-route-agent' : 'bg-raised text-muted',
                )}
              >
                <Database className="size-3.5 shrink-0" />
                {data == null
                  ? 'Checking where memory is stored'
                  : !data.enabled
                    ? 'Long-term memory is switched off (LONG_TERM_MEMORY=off).'
                    : persistent
                      ? 'Saved in PostgreSQL, so it survives restarts.'
                      : 'Kept in server memory until PostgreSQL is reachable; clears when the server restarts.'}
              </p>
              <form onSubmit={add} className="mt-3 flex items-center gap-2">
                <label htmlFor="memory-add" className="sr-only">
                  Add a memory
                </label>
                <input
                  id="memory-add"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  maxLength={300}
                  placeholder="Add something to remember"
                  className="min-w-0 flex-1 rounded-xl border border-line bg-raised/60 px-3 py-2 text-[14px] text-ink outline-none placeholder:text-faint focus:border-line-strong"
                />
                <button
                  type="submit"
                  disabled={saving || draft.trim().length < 2}
                  className="inline-flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-accent-ink transition-opacity disabled:opacity-35"
                  aria-label="Save memory"
                >
                  {saving ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
                </button>
              </form>
            </div>

            <div className="scroll-quiet mt-4 min-h-0 flex-1 overflow-y-auto px-3 pb-3">
              {loading && !data ? (
                <p className="flex items-center gap-2 px-2 py-6 text-[14px] text-muted">
                  <Loader2 className="size-4 animate-spin" /> Loading
                </p>
              ) : items.length === 0 ? (
                <p className="px-2 py-6 text-[14px] leading-relaxed text-muted">
                  Nothing yet. Tell {app} something about yourself, like "I'm Kanish and I work in Python", or say "remember
                  that I prefer short answers".
                </p>
              ) : (
                <ul className="space-y-1">
                  {items.map((m) => (
                    <li key={m.id} className="group flex items-start gap-3 rounded-xl px-2 py-2 hover:bg-raised">
                      <span className="mt-[7px] size-1.5 shrink-0 rounded-full bg-accent" aria-hidden />
                      <div className="min-w-0 flex-1">
                        <p className="text-[14px] leading-snug text-ink">{m.content}</p>
                        <p className="mt-0.5 text-[12px] text-faint">
                          {m.source === 'manual' ? 'Added by you' : 'Learned in a chat'}
                          {when(m.updated_at) ? `, ${when(m.updated_at)}` : ''}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => void remove(m.id)}
                        className="rounded-lg p-1.5 text-faint opacity-100 hover:text-danger sm:opacity-0 sm:group-hover:opacity-100 sm:focus:opacity-100"
                        aria-label={`Forget: ${m.content}`}
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {items.length > 0 && (
              <div className="flex items-center justify-between border-t border-line px-5 py-3 text-[13px]">
                <span className="text-faint">
                  {items.length} {items.length === 1 ? 'memory' : 'memories'}
                </span>
                {confirmClear ? (
                  <span className="flex items-center gap-2">
                    <button type="button" onClick={() => void clearAll()} className="rounded-lg px-2.5 py-1 font-semibold text-danger hover:bg-danger/10">
                      Forget all
                    </button>
                    <button type="button" onClick={() => setConfirmClear(false)} className="rounded-lg px-2.5 py-1 text-muted hover:text-ink">
                      Keep
                    </button>
                  </span>
                ) : (
                  <button type="button" onClick={() => setConfirmClear(true)} className="rounded-lg px-2.5 py-1 text-muted hover:text-danger">
                    Forget all
                  </button>
                )}
              </div>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
