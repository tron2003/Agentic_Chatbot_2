import { useEffect, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { ArrowUpRight, Check, FileSpreadsheet, FileText, FolderOpen, Loader2, Pencil, Plus, Trash2, X } from 'lucide-react';
import { Composer } from './Composer';
import { useChat } from '@/lib/chat-store';
import { ROUTE_LABEL, type Route } from '@/lib/types';
import { boardTime, cn, formatBytes } from '@/lib/utils';

const LINE: Record<Route, string> = { chat: 'var(--route-chat)', rag: 'var(--route-docs)', agent: 'var(--route-agent)' };
const SHEET = /\.(xlsx|xlsm|xls|csv|tsv)$/i;

/** The project's name, renamed in place. */
function ProjectName({ id, name }: { id: string; name: string }) {
  const { updateProject } = useChat();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(name);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => setValue(name), [name]);
  useEffect(() => {
    if (editing) input.current?.select();
  }, [editing]);

  const commit = async () => {
    const v = value.trim();
    setEditing(false);
    if (v && v !== name) {
      if (!(await updateProject(id, { name: v }))) setValue(name);
    } else setValue(name);
  };

  if (editing) {
    return (
      <input
        ref={input}
        value={value}
        maxLength={80}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => void commit()}
        onKeyDown={(e) => {
          if (e.key === 'Enter') void commit();
          if (e.key === 'Escape') {
            setValue(name);
            setEditing(false);
          }
        }}
        aria-label="Project name"
        className="w-full min-w-0 rounded-lg border border-line-strong bg-raised px-2 text-[clamp(1.9rem,4vw,2.9rem)] font-[820] leading-tight tracking-[-0.03em] text-ink outline-none"
      />
    );
  }
  return (
    <button type="button" onClick={() => setEditing(true)} className="group flex min-w-0 items-center gap-3 text-left" title="Rename">
      <h1 className="truncate text-[clamp(1.9rem,4vw,2.9rem)] font-[820] leading-tight tracking-[-0.03em] text-ink">{name}</h1>
      <Pencil className="size-4 shrink-0 text-faint opacity-0 transition-opacity group-hover:opacity-100" />
    </button>
  );
}

/** What the assistant should keep in mind in every chat of this project. */
function Instructions({ id, value }: { id: string; value: string }) {
  const { updateProject } = useChat();
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  useEffect(() => setDraft(value), [value]);
  const dirty = draft.trim() !== value.trim();

  const save = async () => {
    setSaving(true);
    const ok = await updateProject(id, { instructions: draft.trim() });
    setSaving(false);
    if (ok) {
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1800);
    }
  };

  return (
    <section className="border-t border-line pt-3.5">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-[14px] font-semibold text-ink">Instructions</h2>
        {saved && (
          <span className="inline-flex items-center gap-1 text-[12.5px] text-route-agent">
            <Check className="size-3.5" /> Saved
          </span>
        )}
      </div>
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        maxLength={8000}
        rows={5}
        placeholder="How should answers work in this project? For example: I'm writing my thesis on graph neural networks. Answer in British English and cite chapter numbers."
        className="block w-full resize-y rounded-xl border border-line bg-raised/70 px-3 py-2.5 text-[14px] leading-relaxed text-ink outline-none placeholder:text-faint focus:border-line-strong"
      />
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={() => void save()}
          disabled={!dirty || saving}
          className="inline-flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 text-[13px] font-semibold text-bg disabled:opacity-35"
        >
          {saving && <Loader2 className="size-3.5 animate-spin" />}
          Save instructions
        </button>
        {dirty && (
          <button type="button" onClick={() => setDraft(value)} className="rounded-lg px-2 py-1.5 text-[13px] text-muted hover:text-ink">
            Undo changes
          </button>
        )}
      </div>
      <p className="mt-2 text-[12.5px] leading-snug text-faint">Every chat in this project follows these, alongside what it remembers about you.</p>
    </section>
  );
}

/**
 * A project's home: its name, instructions, files and chats. A message sent from here starts
 * a chat inside the project, which searches only these files.
 */
export function ProjectHome({ onOpenLibrary }: { onOpenLibrary: () => void }) {
  const { activeProject, activeProjectId, conversations, scopedDocuments, open, removeDocument, deleteProject, projects } = useChat();
  const reduced = useReducedMotion();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const project = activeProject;
  const chats = conversations.filter((c) => c.project_id === activeProjectId);
  const now = new Date();

  useEffect(() => {
    if (!confirmDelete) return;
    const t = window.setTimeout(() => setConfirmDelete(false), 5000);
    return () => window.clearTimeout(t);
  }, [confirmDelete]);

  if (!project) {
    return (
      <div className="mx-auto max-w-[760px] px-6 pt-28 text-muted">
        {projects.length ? "This project doesn't exist anymore." : <Loader2 className="size-5 animate-spin" />}
      </div>
    );
  }

  const enter = (delay: number) =>
    reduced ? {} : { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.4, delay, ease: [0.2, 0.7, 0.2, 1] as const } };

  return (
    <div className="mx-auto flex min-h-full w-full max-w-[1080px] flex-col px-4 pb-10 pt-20 sm:px-8 lg:pt-24">
      <motion.header {...enter(0)} className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
        <div className="min-w-0 flex-1">
          <p className="mb-1 flex items-center gap-1.5 text-[13.5px] text-muted">
            <FolderOpen className="size-4 text-route-docs" /> Project
          </p>
          <ProjectName id={project.id} name={project.name} />
          <p className="mt-2 text-[14.5px] text-muted">
            {chats.length} {chats.length === 1 ? 'chat' : 'chats'}, {scopedDocuments.length} {scopedDocuments.length === 1 ? 'file' : 'files'}.
            Chats here search only this project's files.
          </p>
        </div>
        {confirmDelete ? (
          <div className="flex items-center gap-2 text-[13px]">
            <span className="text-muted">Delete its chats and files too?</span>
            <button
              type="button"
              disabled={deleting}
              onClick={async () => {
                setDeleting(true);
                await deleteProject(project.id);
                setDeleting(false);
              }}
              className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 font-semibold text-danger hover:bg-danger/10"
            >
              {deleting && <Loader2 className="size-3.5 animate-spin" />} Delete project
            </button>
            <button type="button" onClick={() => setConfirmDelete(false)} className="rounded-lg px-2 py-1.5 text-muted hover:text-ink">
              Keep
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] text-muted hover:bg-danger/10 hover:text-danger"
          >
            <Trash2 className="size-3.5" /> Delete project
          </button>
        )}
      </motion.header>

      <motion.div {...enter(0.06)} className="mt-7">
        <Composer key={project.id} autoFocus placeholder={`Message ${project.name}`} />
      </motion.div>

      <div className="mt-10 grid gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <motion.section {...enter(0.12)} aria-labelledby="project-chats">
          <h2 id="project-chats" className="mb-1 text-[14px] font-semibold text-ink">
            Chats in this project
          </h2>
          {chats.length === 0 ? (
            <p className="border-t border-line pt-4 text-[14px] leading-relaxed text-muted">
              No chats yet. Ask something above; the chat will stay in this project and use its files and instructions.
            </p>
          ) : (
            <ol className="border-t border-line">
              {chats.map((c, i) => {
                const route = (c.last_route ?? null) as Route | null;
                return (
                  <li key={c.id} className="flap-in border-b border-line" style={{ animationDelay: `${80 + i * 60}ms` }}>
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

        <motion.aside {...enter(0.18)} className="space-y-6" aria-label="Project settings">
          <Instructions id={project.id} value={project.instructions} />

          <section className="border-t border-line pt-3.5">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-[14px] font-semibold text-ink">Files</h2>
              <button
                type="button"
                onClick={onOpenLibrary}
                className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[12.5px] text-muted hover:bg-raised hover:text-ink"
              >
                <Plus className="size-3.5" /> Add files
              </button>
            </div>
            {scopedDocuments.length ? (
              <ul className="space-y-1">
                {scopedDocuments.map((d) => (
                  <li key={d.id} className="group flex items-center gap-2 rounded-lg py-1 text-[14px] text-ink">
                    {SHEET.test(d.name) ? <FileSpreadsheet className="size-3.5 shrink-0 text-route-agent" /> : <FileText className="size-3.5 shrink-0 text-route-docs" />}
                    <span className="min-w-0 flex-1 truncate" title={d.name}>
                      {d.name}
                    </span>
                    <span className="shrink-0 text-[12px] text-faint">{formatBytes(d.size_bytes)}</span>
                    <button
                      type="button"
                      onClick={() => void removeDocument(d.id)}
                      className={cn('rounded p-1 text-faint hover:text-danger', 'opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus:opacity-100')}
                      aria-label={`Remove ${d.name} from the project`}
                    >
                      <X className="size-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[13.5px] leading-relaxed text-muted">
                Add PDFs, Word files or spreadsheets. Only chats in this project can read them.
              </p>
            )}
          </section>
        </motion.aside>
      </div>
    </div>
  );
}
