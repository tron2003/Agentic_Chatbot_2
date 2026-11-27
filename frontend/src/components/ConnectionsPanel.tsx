import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  Cable, ChevronDown, Globe, Loader2, Pencil, Plus, RefreshCw, Terminal, Trash2, TriangleAlert, Wrench, X,
} from 'lucide-react';
import { api, ApiError } from '@/lib/api';
import { useChat } from '@/lib/chat-store';
import type { ConnectionServer, ConnectionsInfo, ConnectionTool, ServerDraft, ToolSetting } from '@/lib/types';
import { APP_NAME_FALLBACK, cn, hostname } from '@/lib/utils';

const STATUS: Record<ConnectionServer['status'], { label: string; color: string }> = {
  connected: { label: 'Connected', color: 'var(--route-agent)' },
  connecting: { label: 'Connecting', color: 'var(--signal)' },
  failed: { label: "Couldn't connect", color: 'var(--danger)' },
  skipped: { label: 'Not started', color: 'var(--route-docs)' },
  disabled: { label: 'Off', color: 'var(--line-strong)' },
  idle: { label: 'Not connected yet', color: 'var(--line-strong)' },
};

const SETTINGS: { id: ToolSetting; label: string; hint: string }[] = [
  { id: 'auto', label: 'Always allow', hint: 'Runs without asking' },
  { id: 'ask', label: 'Ask first', hint: 'Waits for your OK in the chat' },
  { id: 'off', label: 'Off', hint: 'The assistant never sees this tool' },
];

function effective(t: ConnectionTool): ToolSetting {
  if (t.setting) return t.setting;
  return t.decision === 'run' ? 'auto' : t.decision;
}

function Switch({ on, onChange, label, disabled }: { on: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!on)}
      className={cn(
        'relative inline-flex h-[22px] w-[38px] shrink-0 items-center rounded-full border transition-colors disabled:opacity-40',
        on ? 'border-route-agent bg-route-agent' : 'border-line-strong bg-sunk',
      )}
    >
      <span className={cn('inline-block size-4 rounded-full bg-white shadow transition-transform', on ? 'translate-x-[18px]' : 'translate-x-[2px]')} />
    </button>
  );
}

function ToolRow({ tool, onSet }: { tool: ConnectionTool; onSet: (key: string, setting: ToolSetting | null) => void }) {
  const current = effective(tool);
  return (
    <li className="flex flex-col gap-2 py-2.5 sm:flex-row sm:items-start sm:gap-4">
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[13px] text-ink">{tool.name}</span>
          <span
            className={cn(
              'rounded px-1.5 text-[11.5px] font-semibold',
              tool.kind === 'act' ? 'bg-signal/12 text-signal' : 'bg-route-agent/12 text-route-agent',
            )}
            title={tool.kind === 'act' ? 'Changes something: sends, creates, deletes or writes' : 'Only looks things up'}
          >
            {tool.kind === 'act' ? 'Acts' : 'Reads'}
          </span>
          {tool.setting && (
            <button type="button" onClick={() => onSet(tool.key, null)} className="text-[12px] text-faint underline-offset-2 hover:text-ink hover:underline">
              Reset to default
            </button>
          )}
        </p>
        {tool.description ? <p className="mt-0.5 line-clamp-2 text-[12.5px] leading-snug text-muted">{tool.description}</p> : null}
      </div>
      <div role="radiogroup" aria-label={`When to run ${tool.name}`} className="flex shrink-0 rounded-lg border border-line bg-bg/50 p-0.5">
        {SETTINGS.map((s) => (
          <button
            key={s.id}
            type="button"
            role="radio"
            aria-checked={current === s.id}
            title={s.hint}
            onClick={() => current !== s.id && onSet(tool.key, s.id)}
            className={cn(
              'rounded-md px-2 py-1 text-[12px] whitespace-nowrap',
              current === s.id
                ? s.id === 'ask'
                  ? 'bg-signal font-semibold text-white'
                  : s.id === 'off'
                    ? 'bg-line-strong font-semibold text-ink'
                    : 'bg-raised font-semibold text-ink shadow-lift'
                : 'text-muted hover:text-ink',
            )}
          >
            {s.label}
          </button>
        ))}
      </div>
    </li>
  );
}

function ServerItem({
  server, onChanged, onRemoved, onEdit, onSetTool,
}: {
  server: ConnectionServer;
  onChanged: (s: ConnectionServer) => void;
  onRemoved: (name: string) => void;
  onEdit: (s: ConnectionServer) => void;
  onSetTool: (key: string, setting: ToolSetting | null) => void;
}) {
  const { toast } = useChat();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<'switch' | 'reconnect' | 'delete' | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const st = STATUS[server.status] ?? STATUS.idle;
  const where = server.transport === 'stdio' ? [server.command, ...server.args].filter(Boolean).join(' ') : hostname(server.url) || server.url;

  const run = async (kind: 'switch' | 'reconnect' | 'delete', fn: () => Promise<void>) => {
    setBusy(kind);
    try {
      await fn();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'That did not work.', 'error');
    } finally {
      setBusy(null);
    }
  };

  return (
    <li className="relative overflow-hidden rounded-xl border border-line bg-raised">
      <span aria-hidden className="absolute inset-y-0 left-0 w-1" style={{ background: st.color }} />
      <div className="flex items-start gap-3 py-3 pl-4 pr-3">
        <span className="mt-0.5 text-muted">{server.transport === 'stdio' ? <Terminal className="size-4" /> : <Globe className="size-4" />}</span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-[15px] font-semibold text-ink">{server.label}</span>
            {server.origin === 'file' && <span className="text-[12px] text-faint">from mcp_servers.yaml</span>}
          </p>
          <p className="truncate font-mono text-[12px] text-faint" title={where ?? ''}>
            {where}
          </p>
          <p className="mt-1 text-[12.5px]" style={{ color: st.color === 'var(--line-strong)' ? 'var(--text-muted)' : st.color }}>
            {busy === 'switch' || busy === 'reconnect' ? 'Connecting…' : st.label}
            {server.status === 'connected' ? `, ${server.tools.length} ${server.tools.length === 1 ? 'tool' : 'tools'}` : ''}
            {server.detail && server.status !== 'connected' ? <span className="text-muted">: {server.detail}</span> : null}
          </p>
        </div>
        <Switch
          on={server.enabled}
          label={`${server.enabled ? 'Turn off' : 'Turn on'} ${server.label}`}
          disabled={!!busy}
          onChange={(v) => run('switch', async () => onChanged(await api.switchConnection(server.name, v)))}
        />
      </div>
      <div className="flex flex-wrap items-center gap-1 border-t border-line px-3 py-1.5 pl-4">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          disabled={!server.tools.length}
          aria-expanded={open}
          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[12.5px] text-muted hover:bg-sunk hover:text-ink disabled:opacity-40 disabled:hover:bg-transparent"
        >
          <Wrench className="size-3.5" /> Tools
          <ChevronDown className={cn('size-3.5 transition-transform', open && 'rotate-180')} />
        </button>
        <button
          type="button"
          disabled={!!busy || !server.enabled}
          onClick={() => run('reconnect', async () => onChanged(await api.reconnect(server.name)))}
          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[12.5px] text-muted hover:bg-sunk hover:text-ink disabled:opacity-40"
        >
          <RefreshCw className={cn('size-3.5', busy === 'reconnect' && 'animate-spin')} /> Reconnect
        </button>
        {server.editable && (
          <>
            <button type="button" onClick={() => onEdit(server)} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[12.5px] text-muted hover:bg-sunk hover:text-ink">
              <Pencil className="size-3.5" /> Edit
            </button>
            {confirmDelete ? (
              <span className="ml-auto flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => run('delete', async () => {
                    await api.removeConnection(server.name);
                    onRemoved(server.name);
                  })}
                  className="rounded-md px-2 py-1 text-[12.5px] font-semibold text-danger hover:bg-danger/10"
                >
                  Remove {server.label}
                </button>
                <button type="button" onClick={() => setConfirmDelete(false)} className="rounded-md px-2 py-1 text-[12.5px] text-muted hover:text-ink">
                  Keep
                </button>
              </span>
            ) : (
              <button type="button" onClick={() => setConfirmDelete(true)} className="ml-auto inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[12.5px] text-muted hover:bg-danger/10 hover:text-danger">
                <Trash2 className="size-3.5" /> Remove
              </button>
            )}
          </>
        )}
      </div>
      <AnimatePresence initial={false}>
        {open && server.tools.length > 0 && (
          <motion.ul
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="divide-y divide-line overflow-hidden border-t border-line px-4"
          >
            {server.tools.map((t) => (
              <ToolRow key={t.key} tool={t} onSet={onSetTool} />
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </li>
  );
}

type Pair = { k: string; v: string };
const toPairs = (o?: Record<string, string>): Pair[] => Object.entries(o ?? {}).map(([k, v]) => ({ k, v }));
const fromPairs = (p: Pair[]) => Object.fromEntries(p.filter((x) => x.k.trim()).map((x) => [x.k.trim(), x.v]));

function Pairs({ label, pairs, onChange, keyHint, valueHint }: { label: string; pairs: Pair[]; onChange: (p: Pair[]) => void; keyHint: string; valueHint: string }) {
  return (
    <fieldset>
      <legend className="mb-1 text-[13px] font-semibold text-ink">{label}</legend>
      <div className="space-y-1.5">
        {pairs.map((p, i) => (
          <div key={i} className="flex gap-1.5">
            <input
              value={p.k}
              onChange={(e) => onChange(pairs.map((x, j) => (j === i ? { ...x, k: e.target.value } : x)))}
              placeholder={keyHint}
              aria-label={`${label} name`}
              className="w-[40%] min-w-0 rounded-lg border border-line bg-bg px-2.5 py-1.5 font-mono text-[12.5px] text-ink outline-none focus:border-line-strong"
            />
            <input
              value={p.v}
              onChange={(e) => onChange(pairs.map((x, j) => (j === i ? { ...x, v: e.target.value } : x)))}
              placeholder={valueHint}
              aria-label={`${label} value`}
              className="min-w-0 flex-1 rounded-lg border border-line bg-bg px-2.5 py-1.5 font-mono text-[12.5px] text-ink outline-none focus:border-line-strong"
            />
            <button type="button" onClick={() => onChange(pairs.filter((_, j) => j !== i))} className="rounded-md p-1.5 text-faint hover:text-danger" aria-label="Remove row">
              <X className="size-3.5" />
            </button>
          </div>
        ))}
        <button type="button" onClick={() => onChange([...pairs, { k: '', v: '' }])} className="inline-flex items-center gap-1 text-[12.5px] text-muted hover:text-ink">
          <Plus className="size-3.5" /> Add
        </button>
      </div>
    </fieldset>
  );
}

function ServerForm({
  initial, stdioAllowed, onSaved, onCancel,
}: {
  initial: ConnectionServer | null;
  stdioAllowed: boolean;
  onSaved: (s: ConnectionServer) => void;
  onCancel: () => void;
}) {
  const { toast } = useChat();
  const editing = !!initial;
  const [name, setName] = useState(initial?.name ?? '');
  const [label, setLabel] = useState(initial?.label ?? '');
  const [transport, setTransport] = useState<ServerDraft['transport']>(initial?.transport ?? 'http');
  const [url, setUrl] = useState(initial?.url ?? '');
  const [headers, setHeaders] = useState<Pair[]>(toPairs(initial?.headers));
  const [command, setCommand] = useState(initial?.command ?? 'npx');
  const [args, setArgs] = useState((initial?.args ?? []).join('\n'));
  const [env, setEnv] = useState<Pair[]>(toPairs(initial?.env));
  const [busy, setBusy] = useState<'test' | 'save' | null>(null);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  const draft = (): ServerDraft => ({
    name: name.trim(),
    label: label.trim() || undefined,
    transport,
    ...(transport === 'stdio'
      ? { command: command.trim(), args: args.split('\n').map((a) => a.trim()).filter(Boolean), env: fromPairs(env) }
      : { url: url.trim(), headers: fromPairs(headers) }),
    enabled: initial?.enabled ?? true,
  });

  const test = async () => {
    setBusy('test');
    setResult(null);
    try {
      const res = await api.testConnection(draft());
      setResult(
        res.status === 'connected'
          ? { ok: true, text: `Connected. It offers ${res.tools.length} ${res.tools.length === 1 ? 'tool' : 'tools'}: ${res.tools.slice(0, 6).map((t) => t.name).join(', ')}${res.tools.length > 6 ? '…' : ''}` }
          : { ok: false, text: res.detail || "Couldn't connect." },
      );
    } catch (err) {
      setResult({ ok: false, text: err instanceof ApiError ? err.message : "Couldn't test the server." });
    } finally {
      setBusy(null);
    }
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy('save');
    try {
      const saved = editing ? await api.updateConnection(initial!.name, draft()) : await api.addConnection(draft());
      toast(saved.status === 'connected' ? `${saved.label} is connected.` : `${saved.label} was saved, but it isn't connected yet.`, saved.status === 'connected' ? 'success' : 'info');
      onSaved(saved);
    } catch (err) {
      setResult({ ok: false, text: err instanceof ApiError ? err.message : "Couldn't save the server." });
    } finally {
      setBusy(null);
    }
  };

  const input = 'w-full rounded-lg border border-line bg-bg px-3 py-2 text-[14px] text-ink outline-none placeholder:text-faint focus:border-line-strong';
  return (
    <form onSubmit={save} className="space-y-3.5 rounded-xl border border-line-strong bg-raised p-4">
      <h3 className="text-[15px] font-semibold text-ink">{editing ? `Edit ${initial!.label}` : 'Add a server'}</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-[13px] font-semibold text-ink">Name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, '-'))}
            disabled={editing}
            required
            pattern="[a-z][a-z0-9_-]{1,39}"
            placeholder="notion"
            className={cn(input, 'font-mono disabled:opacity-60')}
          />
          <span className="mt-1 block text-[12px] text-faint">Lowercase, used in tool settings.</span>
        </label>
        <label className="block">
          <span className="mb-1 block text-[13px] font-semibold text-ink">Display name</span>
          <input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={60} placeholder="Notion" className={input} />
        </label>
      </div>

      <div role="radiogroup" aria-label="How to reach it" className="grid grid-cols-3 gap-1.5">
        {([
          ['http', 'Remote URL', 'Streamable HTTP'],
          ['sse', 'Remote (SSE)', 'Older servers'],
          ['stdio', 'Local command', stdioAllowed ? 'Runs on this server' : 'Turned off here'],
        ] as const).map(([id, title, hint]) => (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={transport === id}
            disabled={id === 'stdio' && !stdioAllowed}
            onClick={() => setTransport(id)}
            className={cn(
              'rounded-lg border px-2.5 py-2 text-left disabled:opacity-45',
              transport === id ? 'border-ink bg-bg' : 'border-line hover:border-line-strong',
            )}
          >
            <span className="block text-[13px] font-semibold text-ink">{title}</span>
            <span className="block text-[11.5px] text-faint">{hint}</span>
          </button>
        ))}
      </div>

      {transport === 'stdio' ? (
        <>
          <label className="block">
            <span className="mb-1 block text-[13px] font-semibold text-ink">Command</span>
            <input value={command} onChange={(e) => setCommand(e.target.value)} required placeholder="npx" className={cn(input, 'font-mono')} />
          </label>
          <label className="block">
            <span className="mb-1 block text-[13px] font-semibold text-ink">Arguments, one per line</span>
            <textarea
              value={args}
              onChange={(e) => setArgs(e.target.value)}
              rows={3}
              placeholder={'-y\n@modelcontextprotocol/server-memory'}
              className={cn(input, 'resize-y font-mono text-[13px]')}
            />
          </label>
          <Pairs label="Environment" pairs={env} onChange={setEnv} keyHint="API_TOKEN" valueHint="${API_TOKEN} or a value" />
        </>
      ) : (
        <>
          <label className="block">
            <span className="mb-1 block text-[13px] font-semibold text-ink">Server URL</span>
            <input value={url} onChange={(e) => setUrl(e.target.value)} required type="url" placeholder="https://mcp.example.com/mcp" className={cn(input, 'font-mono')} />
          </label>
          <Pairs label="Headers" pairs={headers} onChange={setHeaders} keyHint="Authorization" valueHint="Bearer ${NOTION_TOKEN}" />
        </>
      )}
      <p className="text-[12px] leading-snug text-faint">
        Write secrets as <code className="font-mono">{'${VAR}'}</code> and put the value in .env. Values typed here are saved in
        config/connections.json and never sent back to the browser.
      </p>

      {result && (
        <p role="status" className={cn('rounded-lg px-3 py-2 text-[13px] leading-snug', result.ok ? 'bg-route-agent/10 text-route-agent' : 'bg-danger/10 text-danger')}>
          {result.text}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button type="submit" disabled={!!busy} className="inline-flex items-center gap-1.5 rounded-lg bg-ink px-3.5 py-2 text-[13.5px] font-semibold text-bg disabled:opacity-50">
          {busy === 'save' && <Loader2 className="size-4 animate-spin" />}
          {editing ? 'Save changes' : 'Add server'}
        </button>
        <button type="button" onClick={() => void test()} disabled={!!busy || !name} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3.5 py-2 text-[13.5px] font-semibold text-ink hover:border-line-strong disabled:opacity-50">
          {busy === 'test' && <Loader2 className="size-4 animate-spin" />}
          Test connection
        </button>
        <button type="button" onClick={onCancel} className="ml-auto rounded-lg px-3 py-2 text-[13.5px] text-muted hover:text-ink">
          Cancel
        </button>
      </div>
    </form>
  );
}

/**
 * Connections: the MCP servers that give the assistant its tools, and for every tool,
 * whether it runs on its own, waits for approval, or is off.
 */
export function ConnectionsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { toast, meta, refreshMeta } = useChat();
  const [data, setData] = useState<ConnectionsInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState<{ server: ConnectionServer | null } | null>(null);
  const [builtinOpen, setBuiltinOpen] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const app = meta?.app_name ?? APP_NAME_FALLBACK;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.connections());
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Couldn't load connections.", 'error');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (open) {
      void load();
      closeRef.current?.focus();
    } else {
      setForm(null);
    }
  }, [open, load]);

  const upsert = (s: ConnectionServer) => {
    setData((d) => (d ? { ...d, servers: d.servers.some((x) => x.name === s.name) ? d.servers.map((x) => (x.name === s.name ? s : x)) : [...d.servers, s] } : d));
    void refreshMeta();
  };
  const removeServer = (name: string) => {
    setData((d) => (d ? { ...d, servers: d.servers.filter((x) => x.name !== name) } : d));
    void refreshMeta();
  };

  const setTool = async (key: string, setting: ToolSetting | null) => {
    const apply = (t: ConnectionTool): ConnectionTool => {
      if (t.key !== key) return t;
      const def = t.kind === 'act' ? 'ask' : 'run';
      return { ...t, setting, decision: setting === null ? def : setting === 'auto' ? 'run' : setting };
    };
    const prev = data;
    setData((d) => (d ? { ...d, builtin: d.builtin.map(apply), servers: d.servers.map((s) => ({ ...s, tools: s.tools.map(apply) })) } : d));
    try {
      await api.setToolSetting(key, setting);
      void refreshMeta();
    } catch (err) {
      setData(prev);
      toast(err instanceof ApiError ? err.message : "Couldn't change that tool.", 'error');
    }
  };

  const connected = data?.servers.filter((s) => s.status === 'connected') ?? [];
  const toolCount = connected.reduce((n, s) => n + s.tools.length, 0) + (data?.builtin.length ?? 0);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div key="scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px]" onClick={onClose} />
          <motion.aside
            key="panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="connections-title"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 380, damping: 38 }}
            onKeyDown={(e) => e.key === 'Escape' && onClose()}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[580px] flex-col border-l border-line bg-bg shadow-lift"
          >
            <div className="flex items-start justify-between gap-4 px-5 pb-3 pt-5">
              <div>
                <h2 id="connections-title" className="flex items-center gap-2 text-[19px] font-[780] tracking-[-0.01em] text-ink">
                  <Cable className="size-5 text-route-agent" /> Connections
                </h2>
                <p className="mt-1 text-[14px] leading-relaxed text-muted">
                  Servers give {app} more tools. Look-ups run on their own; anything that sends, creates, deletes or writes waits
                  for your OK in the chat. You can change that for each tool.
                </p>
              </div>
              <button ref={closeRef} type="button" onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-raised hover:text-ink" aria-label="Close connections">
                <X className="size-4" />
              </button>
            </div>

            <div className="scroll-quiet min-h-0 flex-1 space-y-4 overflow-y-auto px-5 pb-6">
              {data && (
                <p className="text-[13px] text-faint">
                  {connected.length} of {data.servers.length} {data.servers.length === 1 ? 'server' : 'servers'} connected, {toolCount} tools in all
                </p>
              )}
              {data && !data.approvals && (
                <p className="flex items-start gap-2 rounded-lg bg-signal/10 px-3 py-2 text-[13px] text-signal">
                  <TriangleAlert className="mt-0.5 size-4 shrink-0" /> Approvals are off (TOOL_APPROVALS=off), so every tool runs without asking.
                </p>
              )}
              {data && !data.mcp_enabled && (
                <p className="flex items-start gap-2 rounded-lg bg-raised px-3 py-2 text-[13px] text-muted">
                  <TriangleAlert className="mt-0.5 size-4 shrink-0" /> MCP is off on this server (ENABLE_MCP=false), so servers won't connect.
                </p>
              )}

              {loading && !data ? (
                <p className="flex items-center gap-2 py-6 text-[14px] text-muted">
                  <Loader2 className="size-4 animate-spin" /> Loading
                </p>
              ) : (
                <ul className="space-y-2.5">
                  {data?.servers.map((s) => (
                    <ServerItem key={s.name} server={s} onChanged={upsert} onRemoved={removeServer} onEdit={(srv) => setForm({ server: srv })} onSetTool={setTool} />
                  ))}
                </ul>
              )}

              {form ? (
                <ServerForm
                  key={form.server?.name ?? 'new'}
                  initial={form.server}
                  stdioAllowed={data?.stdio_allowed ?? false}
                  onSaved={(s) => {
                    upsert(s);
                    setForm(null);
                  }}
                  onCancel={() => setForm(null)}
                />
              ) : (
                <button
                  type="button"
                  onClick={() => setForm({ server: null })}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-line-strong py-3 text-[14px] font-semibold text-muted hover:border-ink hover:text-ink"
                >
                  <Plus className="size-4" /> Add a server
                </button>
              )}

              {data && data.builtin.length > 0 && (
                <section className="rounded-xl border border-line bg-raised">
                  <button
                    type="button"
                    onClick={() => setBuiltinOpen((o) => !o)}
                    aria-expanded={builtinOpen}
                    className="flex w-full items-center gap-2 px-4 py-3 text-left"
                  >
                    <Wrench className="size-4 text-muted" />
                    <span className="flex-1 text-[14.5px] font-semibold text-ink">Built-in tools and agents</span>
                    <span className="text-[12.5px] text-faint">{data.builtin.length}</span>
                    <ChevronDown className={cn('size-4 text-muted transition-transform', builtinOpen && 'rotate-180')} />
                  </button>
                  {builtinOpen && (
                    <ul className="divide-y divide-line border-t border-line px-4">
                      {data.builtin.map((t) => (
                        <ToolRow key={t.key} tool={t} onSet={setTool} />
                      ))}
                    </ul>
                  )}
                </section>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
