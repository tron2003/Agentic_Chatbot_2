import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { ArrowUpRight, Brain, Cable, FileSpreadsheet, FileText, Library, Plus } from 'lucide-react';
import { Composer, type ComposerHandle } from './Composer';
import { RouteMap } from './RouteMap';
import { api } from '@/lib/api';
import { useChat } from '@/lib/chat-store';
import { ROUTE_LABEL, type MemoryItem, type Route } from '@/lib/types';
import { APP_NAME_FALLBACK, boardTime, cn, greeting, nameFromMemories } from '@/lib/utils';

const LINE: Record<Route, string> = { chat: 'var(--route-chat)', rag: 'var(--route-docs)', agent: 'var(--route-agent)' };
const SHEET = /\.(xlsx|xlsm|xls|csv|tsv)$/i;

/** The local time, updated on the minute. */
function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    let interval: number | undefined;
    const timeout = window.setTimeout(() => {
      setNow(new Date());
      interval = window.setInterval(() => setNow(new Date()), 60_000);
    }, (60 - new Date().getSeconds()) * 1000);
    return () => {
      window.clearTimeout(timeout);
      if (interval) window.clearInterval(interval);
    };
  }, []);
  return now;
}

/** A small titled block in the side column. The title row carries its own action. */
function Side({ icon, title, action, children }: { icon: ReactNode; title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="border-t border-line pt-3.5">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-muted">{icon}</span>
        <h2 className="flex-1 text-[14px] font-semibold text-ink">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function SideLink({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" onClick={onClick} className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[12.5px] text-muted hover:bg-raised hover:text-ink">
      {children}
    </button>
  );
}

/**
 * Home: a departures board of the user's own work. The greeting uses the name the
 * assistant remembers; recent chats are listed with the route each one took; the side
 * column shows what it knows, the library and the connections, each one click away.
 */
export function Welcome({ onOpenLibrary }: { onOpenLibrary: () => void }) {
  const { meta, documents, conversations, conversationsLoaded, send, open, setMemoryPanelOpen, setConnectionsOpen } = useChat();
  const composer = useRef<ComposerHandle>(null);
  const reduced = useReducedMotion();
  const now = useClock();
  const [memories, setMemories] = useState<MemoryItem[] | null>(null);
  const [hover, setHover] = useState<Route | null>(null);
  const app = meta?.app_name ?? APP_NAME_FALLBACK;
  const memoryOn = meta?.memory?.long_term !== 'off';

  useEffect(() => {
    if (!meta || !memoryOn) return;
    let live = true;
    api.memories().then(
      (m) => live && setMemories(m.items),
      () => live && setMemories([]),
    );
    return () => {
      live = false;
    };
  }, [meta, memoryOn]);

  const name = useMemo(() => nameFromMemories(memories ?? []), [memories]);
  const recent = conversations.slice(0, 6);
  const facts = (memories ?? []).filter((m) => !/^(name is|goes by)/i.test(m.content)).slice(0, 4);
  const nameIsFact = !!name && facts.some((m) => m.content.startsWith(name));
  const sheets = documents.filter((d) => SHEET.test(d.name));
  const files = documents.filter((d) => !SHEET.test(d.name));
  const links = (meta?.integrations?.items ?? []).filter((i) => i.kind === 'mcp' || i.kind === 'agent');
  const linked = links.filter((i) => i.status === 'ok');
  const web = meta?.web_search ?? false;

  // Suggestions from what the user actually has: their files, their sheets, their connections.
  const suggestions = useMemo(() => {
    const out: { route: Route; text: string; action?: () => void }[] = [];
    if (sheets[0]) out.push({ route: 'agent', text: `What are the totals in ${sheets[0].name}?` });
    if (files[0]) out.push({ route: 'rag', text: `Summarize the key points of ${files[0].name}` });
    if (!documents.length) out.push({ route: 'rag', text: 'Add a document, then ask about it', action: onOpenLibrary });
    out.push(
      web
        ? { route: 'agent', text: 'Research the latest LangGraph release and what changed' }
        : { route: 'agent', text: 'How many days are left until 1 January 2027?' },
    );
    if (out.length < 3) out.push({ route: 'chat', text: 'Explain the difference between RAG and fine-tuning' });
    return out.slice(0, 3);
  }, [sheets, files, documents.length, web, onOpenLibrary]);

  const enter = (delay: number) =>
    reduced ? {} : { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.45, delay, ease: [0.2, 0.7, 0.2, 1] as const } };

  const time = now.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  const date = now.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });

  return (
    <div className="mx-auto flex min-h-full w-full max-w-[1080px] flex-col px-4 pb-10 pt-20 sm:px-8 lg:pt-24">
      {/* greeting and clock */}
      <motion.header {...enter(0)} className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
        <div className="min-w-0">
          <h1 className="text-[clamp(2.1rem,4.6vw,3.4rem)] font-[820] leading-[1.02] tracking-[-0.03em] text-ink text-balance">
            {greeting(now)}
            {name ? `, ${name}.` : '.'}
          </h1>
          <p className="mt-2.5 max-w-[60ch] text-[15.5px] leading-relaxed text-muted text-pretty">
            Ask anything. {app} picks the route: a direct answer, your documents, or Deep research with sources.
          </p>
        </div>
        <div className="text-right tabular-nums" aria-label={`${time}, ${date}`}>
          <p className="text-[clamp(1.9rem,3.6vw,2.6rem)] font-[300] leading-none tracking-[-0.02em] text-ink">{time}</p>
          <p className="mt-1.5 text-[13.5px] text-muted">{date}</p>
        </div>
      </motion.header>

      {/* composer and suggestions */}
      <motion.div {...enter(0.08)} className="mt-7">
        <Composer ref={composer} autoFocus placeholder={`Message ${app}, or drop a file`} />
        <ul className="mt-3 flex flex-wrap gap-2" aria-label="Suggestions">
          {suggestions.map((s) => (
            <li key={s.text}>
              <button
                type="button"
                onMouseEnter={() => setHover(s.route)}
                onMouseLeave={() => setHover(null)}
                onClick={() => (s.action ? s.action() : void send(s.text))}
                className="group inline-flex max-w-full items-center gap-2 rounded-full border border-line bg-raised/70 py-1.5 pl-2.5 pr-3.5 text-[13.5px] text-ink transition-colors hover:border-line-strong hover:bg-raised"
              >
                <span className="size-2 shrink-0 rounded-full" style={{ background: LINE[s.route] }} aria-hidden />
                <span className="truncate">{s.text}</span>
              </button>
            </li>
          ))}
        </ul>
      </motion.div>

      <div className="mt-10 grid gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        {/* departures: the user's recent chats */}
        <motion.section {...enter(0.14)} aria-labelledby="board-title">
          <div className="mb-1 flex items-baseline justify-between">
            <h2 id="board-title" className="text-[14px] font-semibold text-ink">
              Recent chats
            </h2>
            {recent.length > 0 && <span className="text-[12.5px] text-faint">{conversations.length} in all</span>}
          </div>

          {!conversationsLoaded ? (
            <div className="h-40" />
          ) : recent.length === 0 ? (
            <div className="border-t border-line pt-4">
              <p className="mb-3 text-[14px] leading-relaxed text-muted">
                No chats yet. Every message takes one of three routes, and your chats will line up here with the route they took.
              </p>
              <div className="-ml-1">
                <RouteMap
                  highlight={hover}
                  labels={ROUTE_LABEL}
                  descriptions={{ chat: 'a direct answer', rag: 'your files, cited', agent: web ? 'plans, searches, cited report' : 'tools (web search off)' }}
                />
              </div>
            </div>
          ) : (
            <ol className="border-t border-line">
              {recent.map((c, i) => {
                const route = (c.last_route ?? null) as Route | null;
                return (
                  <li key={c.id} className="flap-in border-b border-line" style={{ animationDelay: `${120 + i * 70}ms` }}>
                    <button
                      type="button"
                      onClick={() => void open(c.id)}
                      className="group grid w-full grid-cols-[4.75rem_6px_minmax(0,1fr)_auto] items-center gap-x-3.5 py-3 text-left sm:grid-cols-[5.5rem_6px_minmax(0,1fr)_7.5rem_auto]"
                    >
                      <span className="text-[13px] tabular-nums text-muted">{boardTime(c.updated_at, now)}</span>
                      <span className="h-7 w-[6px] rounded-full" style={{ background: route ? LINE[route] : 'var(--line-strong)' }} aria-hidden />
                      <span className="truncate text-[15px] font-medium text-ink group-hover:underline group-hover:decoration-line-strong group-hover:underline-offset-4">
                        {c.title}
                      </span>
                      <span className="hidden text-[12.5px] sm:block" style={{ color: route ? LINE[route] : 'var(--text-faint)' }}>
                        {route ? ROUTE_LABEL[route] : `${c.message_count} ${c.message_count === 1 ? 'message' : 'messages'}`}
                      </span>
                      <ArrowUpRight className="size-4 text-faint opacity-0 transition-opacity group-hover:opacity-100" />
                    </button>
                  </li>
                );
              })}
            </ol>
          )}
        </motion.section>

        {/* what it knows, what it can read, what it can reach */}
        <motion.aside {...enter(0.2)} className="space-y-6" aria-label="Your workspace">
          {memoryOn && (
            <Side
              icon={<Brain className="size-4 text-accent" />}
              title="What I know about you"
              action={<SideLink onClick={() => setMemoryPanelOpen(true)}>{facts.length || name ? 'Edit' : 'Add'}</SideLink>}
            >
              {memories === null ? (
                <div className="h-12" />
              ) : facts.length || name ? (
                <ul className="space-y-1.5">
                  {name && !nameIsFact && <li className="text-[14px] leading-snug text-ink">Your name is {name}</li>}
                  {facts.map((m) => (
                    <li key={m.id} className="line-clamp-2 text-[14px] leading-snug text-ink">
                      {m.content}
                    </li>
                  ))}
                  {(memories?.length ?? 0) > facts.length + (name && !nameIsFact ? 1 : 0) && (
                    <li className="text-[12.5px] text-faint">and {(memories?.length ?? 0) - facts.length - (name && !nameIsFact ? 1 : 0)} more</li>
                  )}
                </ul>
              ) : (
                <p className="text-[13.5px] leading-relaxed text-muted">
                  Nothing yet. Tell me your name, what you're working on, or how you like answers, and I'll keep it in mind in every chat.
                </p>
              )}
            </Side>
          )}

          <Side
            icon={<Library className="size-4 text-route-docs" />}
            title="Your library"
            action={<SideLink onClick={onOpenLibrary}>{documents.length ? 'Open' : <><Plus className="size-3.5" /> Add files</>}</SideLink>}
          >
            {documents.length ? (
              <ul className="space-y-1.5">
                {documents.slice(0, 4).map((d) => (
                  <li key={d.id} className="flex items-center gap-2 text-[14px] text-ink">
                    {SHEET.test(d.name) ? <FileSpreadsheet className="size-3.5 shrink-0 text-route-agent" /> : <FileText className="size-3.5 shrink-0 text-route-docs" />}
                    <span className="truncate">{d.name}</span>
                  </li>
                ))}
                {documents.length > 4 && <li className="text-[12.5px] text-faint">and {documents.length - 4} more</li>}
              </ul>
            ) : (
              <p className="text-[13.5px] leading-relaxed text-muted">
                Add PDFs, Word files or spreadsheets. I'll cite them in answers and run real calculations on the sheets.
              </p>
            )}
          </Side>

          <Side
            icon={<Cable className="size-4 text-route-agent" />}
            title="Connections"
            action={<SideLink onClick={() => setConnectionsOpen(true)}>Manage</SideLink>}
          >
            {links.length ? (
              <ul className="flex flex-wrap gap-1.5">
                {links.map((l) => (
                  <li
                    key={l.name}
                    title={l.detail}
                    className="inline-flex items-center gap-1.5 rounded-full border border-line bg-raised/70 px-2.5 py-0.5 text-[13px] text-ink"
                  >
                    <span className={cn('size-1.5 rounded-full', l.status === 'ok' ? 'bg-route-agent' : l.status === 'failed' || l.status === 'unreachable' ? 'bg-danger' : 'bg-route-docs')} aria-hidden />
                    {l.label}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[13.5px] leading-relaxed text-muted">Connect MCP servers like GitHub or Notion to give me more tools.</p>
            )}
            <p className="mt-2 text-[12.5px] text-faint">
              {meta ? `${meta.tools.length} tools ready${linked.length ? ` across ${linked.length} ${linked.length === 1 ? 'connection' : 'connections'}` : ''}. Actions wait for your OK.` : ''}
            </p>
          </Side>
        </motion.aside>
      </div>
    </div>
  );
}
