import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, Library, Monitor, Moon, Pencil, Plus, Search, Sun, Trash2, X } from 'lucide-react';
import type { ThemeChoice } from '@/hooks/useTheme';
import { useChat } from '@/lib/chat-store';
import type { Conversation, Integration } from '@/lib/types';
import { cn, dateGroup, type DateGroup } from '@/lib/utils';

const GROUP_ORDER: DateGroup[] = ['Today', 'Yesterday', 'Previous 7 days', 'Previous 30 days', 'Older'];

function Row({ c, active, onOpen }: { c: Conversation; active: boolean; onOpen: () => void }) {
  const { rename, remove } = useChat();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(c.title);
  const [confirming, setConfirming] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => setTitle(c.title), [c.title]);
  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);
  useEffect(() => {
    if (!confirming) return;
    const t = window.setTimeout(() => setConfirming(false), 3500);
    return () => window.clearTimeout(t);
  }, [confirming]);

  const commit = () => {
    const t = title.trim();
    setEditing(false);
    if (t && t !== c.title) void rename(c.id, t);
    else setTitle(c.title);
  };

  if (editing) {
    return (
      <div className="flex items-center gap-1 rounded-lg bg-raised px-2 py-1">
        <input
          ref={inputRef}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit();
            if (e.key === 'Escape') {
              setTitle(c.title);
              setEditing(false);
            }
          }}
          onBlur={commit}
          maxLength={120}
          aria-label="Conversation title"
          className="min-w-0 flex-1 bg-transparent py-1 text-[14px] text-ink outline-none"
        />
        <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={commit} className="rounded p-1 text-muted hover:text-ink" aria-label="Save title">
          <Check className="size-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div className={cn('group relative flex items-center rounded-lg', active ? 'bg-raised shadow-lift' : 'hover:bg-raised/60')}>
      <button
        type="button"
        onClick={onOpen}
        aria-current={active ? 'page' : undefined}
        className="min-w-0 flex-1 truncate px-3 py-2 text-left text-[14px] text-ink"
        title={c.title}
      >
        {c.title}
      </button>
      <div className={cn('flex shrink-0 items-center pr-1', confirming ? 'opacity-100' : 'opacity-0 group-focus-within:opacity-100 group-hover:opacity-100')}>
        {confirming ? (
          <>
            <button type="button" onClick={() => void remove(c.id)} className="rounded-md px-2 py-1 text-[12.5px] font-semibold text-danger hover:bg-danger/10">
              Delete
            </button>
            <button type="button" onClick={() => setConfirming(false)} className="rounded p-1 text-muted hover:text-ink" aria-label="Cancel delete">
              <X className="size-3.5" />
            </button>
          </>
        ) : (
          <>
            <button type="button" onClick={() => setEditing(true)} className="rounded p-1.5 text-faint hover:text-ink" aria-label={`Rename ${c.title}`}>
              <Pencil className="size-3.5" />
            </button>
            <button type="button" onClick={() => setConfirming(true)} className="rounded p-1.5 text-faint hover:text-danger" aria-label={`Delete ${c.title}`}>
              <Trash2 className="size-3.5" />
            </button>
          </>
        )}
      </div>
    </div>
  );
}

const KIND_LABEL: Record<Integration['kind'], string> = {
  agent: 'Agent Junction can ask',
  inbound: 'Lets other apps use Junction',
  webhook: 'Sends events',
};

function statusTone(status: string) {
  if (status === 'ok' || status === 'idle') return 'bg-route-agent';
  if (status === 'unknown') return 'bg-line-strong';
  return 'bg-danger';
}

function Connections() {
  const { meta } = useChat();
  const items = meta?.integrations?.items ?? [];
  const error = meta?.integrations?.error;
  if (!items.length && !error) return null;
  return (
    <section className="px-3 pb-1 pt-1" aria-label="Connections">
      <h2 className="pb-1 text-[12.5px] font-semibold text-faint">Connections</h2>
      {error ? <p className="text-[12.5px] leading-snug text-danger">{error}</p> : null}
      <ul className="space-y-0.5">
        {items.map((i) => (
          <li key={i.name} className="flex items-center gap-2 py-0.5" title={`${KIND_LABEL[i.kind]}: ${i.detail} (${i.status})`}>
            <span className={cn('size-2 shrink-0 rounded-full', statusTone(i.status))} aria-hidden />
            <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{i.label}</span>
            <span className="shrink-0 text-[12px] text-faint">{i.status === 'ok' || i.status === 'idle' ? (i.kind === 'agent' ? 'connected' : 'on') : i.status}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Sidebar({
  open,
  onClose,
  onOpenLibrary,
  theme,
  onCycleTheme,
}: {
  open: boolean;
  onClose: () => void;
  onOpenLibrary: () => void;
  theme: ThemeChoice;
  onCycleTheme: () => void;
}) {
  const { conversations, conversationsLoaded, activeId, open: openConversation, newChat, searchConversations, documents, meta, serverDown } = useChat();
  const [query, setQuery] = useState('');

  useEffect(() => {
    const t = window.setTimeout(() => void searchConversations(query.trim()), 250);
    return () => window.clearTimeout(t);
  }, [query, searchConversations]);

  const groups = useMemo(() => {
    const map = new Map<DateGroup, Conversation[]>();
    for (const c of conversations) {
      const g = dateGroup(c.updated_at);
      map.set(g, [...(map.get(g) ?? []), c]);
    }
    return GROUP_ORDER.filter((g) => map.has(g)).map((g) => [g, map.get(g)!] as const);
  }, [conversations]);

  const ThemeIcon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Monitor;
  const themeLabel = theme === 'system' ? 'Theme: system' : theme === 'dark' ? 'Theme: dark' : 'Theme: light';

  return (
    <>
      <div
        className={cn('fixed inset-0 z-30 bg-black/30 backdrop-blur-[2px] transition-opacity lg:hidden', open ? 'opacity-100' : 'pointer-events-none opacity-0')}
        onClick={onClose}
        aria-hidden
      />
      <aside
        className={cn(
          'glass fixed inset-y-0 left-0 z-40 flex w-[284px] flex-col border-r border-line transition-transform duration-300 ease-out',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
        aria-label="Conversations"
      >
        <div className="flex items-center justify-between px-4 pb-3 pt-4">
          <a href="#" onClick={(e) => { e.preventDefault(); newChat(); onClose(); }} className="flex items-center gap-2.5 rounded-lg">
            <img src="/favicon.svg" alt="" className="size-7" />
            <span className="text-[17px] font-[780] tracking-[-0.01em] text-ink">{meta?.app_name ?? 'Junction'}</span>
          </a>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-raised hover:text-ink" aria-label="Close sidebar">
            <X className="size-4" />
          </button>
        </div>

        <div className="space-y-2 px-3">
          <button
            type="button"
            onClick={() => {
              newChat();
              if (window.innerWidth < 1024) onClose();
            }}
            className="flex w-full items-center gap-2 rounded-xl border border-line bg-raised px-3 py-2.5 text-[14px] font-semibold text-ink shadow-lift hover:border-line-strong"
          >
            <Plus className="size-4" /> New chat
            <span className="kbd ml-auto hidden lg:inline">Ctrl K</span>
          </button>
          <label className="flex items-center gap-2 rounded-xl border border-line bg-bg/40 px-3 py-2 focus-within:border-line-strong">
            <Search className="size-4 text-faint" />
            <span className="sr-only">Search conversations</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search conversations"
              className="min-w-0 flex-1 bg-transparent text-[14px] text-ink outline-none placeholder:text-faint"
            />
            {query && (
              <button type="button" onClick={() => setQuery('')} className="text-faint hover:text-ink" aria-label="Clear search">
                <X className="size-3.5" />
              </button>
            )}
          </label>
        </div>

        <nav className="scroll-quiet mt-3 min-h-0 flex-1 overflow-y-auto px-3 pb-3">
          {!conversationsLoaded ? null : groups.length === 0 ? (
            <p className="px-3 py-6 text-[13.5px] leading-relaxed text-muted">
              {query ? `No conversations match "${query}".` : 'Your conversations will appear here.'}
            </p>
          ) : (
            groups.map(([group, items]) => (
              <section key={group} className="mb-3">
                <h2 className="px-3 pb-1 pt-2 text-[12.5px] font-semibold text-faint">{group}</h2>
                <ul className="space-y-0.5">
                  {items.map((c) => (
                    <li key={c.id}>
                      <Row
                        c={c}
                        active={c.id === activeId}
                        onOpen={() => {
                          void openConversation(c.id);
                          if (window.innerWidth < 1024) onClose();
                        }}
                      />
                    </li>
                  ))}
                </ul>
              </section>
            ))
          )}
        </nav>

        <div className="space-y-1 border-t border-line p-3">
          <button type="button" onClick={onOpenLibrary} className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[14px] text-ink hover:bg-raised">
            <Library className="size-4 text-route-docs" />
            Document library
            <span className="ml-auto text-[12.5px] text-faint">{documents.length || ''}</span>
          </button>
          <Connections />
          <div className="flex items-center gap-2 px-3 py-1.5">
            <span
              className={cn('size-2 shrink-0 rounded-full', serverDown ? 'bg-danger' : meta?.llm_ready ? 'bg-route-agent' : 'bg-route-docs')}
              aria-hidden
            />
            <span className="min-w-0 flex-1 truncate text-[12.5px] text-muted" title={meta?.llm_error ?? undefined}>
              {serverDown ? 'Server unreachable' : meta ? (meta.llm_ready ? meta.model.model : 'Model not configured') : 'Connecting'}
            </span>
            <button type="button" onClick={onCycleTheme} className="rounded-md p-1.5 text-muted hover:bg-raised hover:text-ink" aria-label={themeLabel} title={themeLabel}>
              <ThemeIcon className="size-4" />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
