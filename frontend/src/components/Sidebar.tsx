import { useEffect, useMemo, useRef, useState } from 'react';
import { Brain, Cable, Check, ChevronsUpDown, Folder, FolderOpen, FolderPlus, Library, Monitor, Moon, Pencil, Plus, Search, Sun, Trash2, X } from 'lucide-react';
import type { ThemeChoice } from '@/hooks/useTheme';
import { useChat } from '@/lib/chat-store';
import type { Conversation, Integration } from '@/lib/types';
import { TYPING_SPEEDS } from '@/lib/typing';
import { APP_NAME_FALLBACK, cn, dateGroup, type DateGroup } from '@/lib/utils';

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

function kindLabel(kind: Integration['kind'], app: string): string {
  return { agent: `Agent ${app} can ask`, inbound: `Lets other apps use ${app}`, webhook: 'Sends events', mcp: 'MCP server' }[kind];
}

function statusTone(status: string) {
  if (status === 'ok' || status === 'idle') return 'bg-route-agent';
  if (status === 'unknown') return 'bg-line-strong';
  if (status === 'skipped' || status === 'disabled' || status === 'connecting') return 'bg-route-docs';
  return 'bg-danger';
}

function Connections() {
  const { meta, setConnectionsOpen } = useChat();
  const items = meta?.integrations?.items ?? [];
  const error = meta?.integrations?.error;
  const app = meta?.app_name ?? APP_NAME_FALLBACK;
  return (
    <section className="px-3 pb-1 pt-1" aria-label="Connections">
      <div className="flex items-center justify-between pb-1">
        <h2 className="text-[12.5px] font-semibold text-faint">Connections</h2>
        <button
          type="button"
          onClick={() => setConnectionsOpen(true)}
          className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[12px] text-muted hover:bg-raised hover:text-ink"
        >
          <Cable className="size-3.5" /> Manage
        </button>
      </div>
      {error ? <p className="text-[12.5px] leading-snug text-danger">{error}</p> : null}
      {items.length ? (
        <ul className="space-y-0.5">
          {items.slice(0, 6).map((i) => (
            <li key={i.name} className="flex items-center gap-2 py-0.5" title={`${kindLabel(i.kind, app)}: ${i.detail} (${i.status})`}>
              <span className={cn('size-2 shrink-0 rounded-full', statusTone(i.status))} aria-hidden />
              <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{i.label}</span>
              <span className="shrink-0 text-[12px] text-faint">
                {i.status === 'ok' || i.status === 'idle' ? (i.kind === 'mcp' ? i.detail : i.kind === 'agent' ? 'connected' : 'on') : i.status}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <button type="button" onClick={() => setConnectionsOpen(true)} className="text-left text-[12.5px] leading-snug text-muted hover:text-ink">
          Add MCP servers to give {app} more tools.
        </button>
      )}
    </section>
  );
}

/** Projects: workspaces with their own chats, files and instructions. */
function Projects({ onNavigate }: { onNavigate: () => void }) {
  const { projects, activeProjectId, openProject, createProject } = useChat();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (adding) input.current?.focus();
  }, [adding]);

  const create = async () => {
    const n = name.trim();
    if (!n) {
      setAdding(false);
      return;
    }
    setBusy(true);
    const p = await createProject(n);
    setBusy(false);
    if (p) {
      setName('');
      setAdding(false);
      onNavigate();
    }
  };

  return (
    <section className="mb-2" aria-label="Projects">
      <div className="flex items-center justify-between px-3 pb-1 pt-2">
        <h2 className="text-[12.5px] font-semibold text-faint">Projects</h2>
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[12px] text-muted hover:bg-raised hover:text-ink"
        >
          <FolderPlus className="size-3.5" /> New
        </button>
      </div>
      {adding && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void create();
          }}
          className="mb-1 flex items-center gap-1 rounded-lg bg-raised px-2 py-1"
        >
          <FolderOpen className="size-4 shrink-0 text-route-docs" />
          <input
            ref={input}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && (setAdding(false), setName(''))}
            onBlur={() => !name.trim() && setAdding(false)}
            maxLength={80}
            placeholder="Project name"
            aria-label="New project name"
            className="min-w-0 flex-1 bg-transparent py-1 text-[14px] text-ink outline-none placeholder:text-faint"
          />
          <button type="submit" disabled={busy || !name.trim()} className="rounded p-1 text-muted hover:text-ink disabled:opacity-40" aria-label="Create project">
            <Check className="size-3.5" />
          </button>
        </form>
      )}
      {projects.length === 0 && !adding ? (
        <button type="button" onClick={() => setAdding(true)} className="px-3 py-1 text-left text-[13px] leading-snug text-muted hover:text-ink">
          Group chats and files around one topic, with its own instructions.
        </button>
      ) : (
        <ul className="space-y-0.5">
          {projects.map((p) => {
            const active = p.id === activeProjectId;
            const Icon = active ? FolderOpen : Folder;
            return (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => {
                    openProject(p.id);
                    onNavigate();
                  }}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[14px] text-ink',
                    active ? 'bg-raised shadow-lift' : 'hover:bg-raised/60',
                  )}
                >
                  <Icon className="size-4 shrink-0 text-route-docs" />
                  <span className="min-w-0 flex-1 truncate">{p.name}</span>
                  <span className="shrink-0 text-[12px] text-faint">{p.chat_count || ''}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function TypingSpeedControl() {
  const { typingSpeed, setTypingSpeed } = useChat();
  return (
    <section className="px-3 pb-1 pt-1">
      <h2 id="typing-speed-label" className="pb-1 text-[12.5px] font-semibold text-faint">
        Typing speed
      </h2>
      <div role="group" aria-labelledby="typing-speed-label" className="flex rounded-lg border border-line bg-bg/40 p-0.5">
        {TYPING_SPEEDS.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setTypingSpeed(s.id)}
            aria-pressed={typingSpeed === s.id}
            title={s.id === 'instant' ? 'Show answers as fast as they arrive' : `About ${s.cps} characters per second`}
            className={cn(
              'flex-1 rounded-md py-1 text-[12.5px]',
              typingSpeed === s.id ? 'bg-raised font-semibold text-ink shadow-lift' : 'text-muted hover:text-ink',
            )}
          >
            {s.label}
          </button>
        ))}
      </div>
    </section>
  );
}

export function Sidebar({
  open,
  onClose,
  onOpenLibrary,
  onOpenMemory,
  theme,
  onCycleTheme,
}: {
  open: boolean;
  onClose: () => void;
  onOpenLibrary: () => void;
  onOpenMemory: () => void;
  theme: ThemeChoice;
  onCycleTheme: () => void;
}) {
  const {
    conversations, conversationsLoaded, activeId, open: openConversation, newChat, searchConversations, scopedDocuments: documents, meta, serverDown,
    setModelPickerOpen,
  } = useChat();
  const [query, setQuery] = useState('');

  useEffect(() => {
    const t = window.setTimeout(() => void searchConversations(query.trim()), 250);
    return () => window.clearTimeout(t);
  }, [query, searchConversations]);

  const groups = useMemo(() => {
    const map = new Map<DateGroup, Conversation[]>();
    // Project chats live on their project's page; a search looks through every chat.
    for (const c of conversations.filter((x) => query.trim() || !x.project_id)) {
      const g = dateGroup(c.updated_at);
      map.set(g, [...(map.get(g) ?? []), c]);
    }
    return GROUP_ORDER.filter((g) => map.has(g)).map((g) => [g, map.get(g)!] as const);
  }, [conversations, query]);

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
            <span className="text-[17px] font-[780] tracking-[-0.01em] text-ink">{meta?.app_name ?? APP_NAME_FALLBACK}</span>
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
          {!query && <Projects onNavigate={() => window.innerWidth < 1024 && onClose()} />}
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
          <button
            type="button"
            onClick={onOpenMemory}
            className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[14px] text-ink hover:bg-raised"
            title={
              meta?.memory?.long_term === 'postgres'
                ? 'What the assistant remembers about you, saved in PostgreSQL'
                : meta?.memory?.long_term === 'off'
                  ? 'Long-term memory is switched off'
                  : 'What the assistant remembers about you (kept in server memory until PostgreSQL is reachable)'
            }
          >
            <Brain className="size-4 text-accent" />
            Memory
            {meta?.memory?.long_term && meta.memory.long_term !== 'off' && (
              <span className="ml-auto text-[12px] text-faint">{meta.memory.long_term === 'postgres' ? 'Postgres' : 'in memory'}</span>
            )}
          </button>
          <Connections />
          <TypingSpeedControl />
          <div className="flex items-center gap-1 px-1.5 py-0.5">
            <button
              type="button"
              onClick={() => setModelPickerOpen(true)}
              disabled={serverDown || !meta}
              className="group/model flex min-h-[36px] min-w-0 flex-1 items-center gap-2 rounded-lg px-1.5 text-left transition hover:bg-raised disabled:cursor-default disabled:hover:bg-transparent"
              title={meta?.llm_error ?? (meta ? `${meta.model.provider}: ${meta.model.model}. Click to change.` : undefined)}
              aria-label={meta?.llm_ready ? `Model: ${meta.model.model}. Change model` : 'Choose a model'}
            >
              <span
                className={cn('size-2 shrink-0 rounded-full', serverDown ? 'bg-danger' : meta?.llm_ready ? 'bg-route-agent' : 'bg-route-docs')}
                aria-hidden
              />
              <span className="min-w-0 flex-1 truncate text-[12.5px] text-muted group-hover/model:text-ink">
                {serverDown ? 'Server unreachable' : meta ? (meta.llm_ready ? meta.model.model : 'Choose a model') : 'Connecting'}
              </span>
              {meta && !serverDown && <ChevronsUpDown className="size-3.5 shrink-0 text-faint group-hover/model:text-ink" />}
            </button>
            <button type="button" onClick={onCycleTheme} className="rounded-md p-1.5 text-muted hover:bg-raised hover:text-ink" aria-label={themeLabel} title={themeLabel}>
              <ThemeIcon className="size-4" />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
