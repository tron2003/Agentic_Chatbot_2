import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, ApiError, setApiKey as persistApiKey, streamApproval, streamChat } from './api';
import type {
  ApprovalRecord, Attachment, ChatMode, Conversation, DocumentInfo, Meta, Project, Step, StoredMessage, StreamEvent,
  UIMessage, UploadResponse,
} from './types';
import { charsPerSecond, readTypingSpeed, saveTypingSpeed, Typewriter, type TypingSpeed } from './typing';
import { fromStored, uid } from './utils';

export interface Toast {
  id: string;
  kind: 'info' | 'error' | 'success';
  text: string;
}

interface ChatState {
  meta: Meta | null;
  serverDown: boolean;
  conversations: Conversation[];
  conversationsLoaded: boolean;
  activeId: string | null;
  /**
   * Whether the open conversation has any messages. The messages themselves
   * live in a separate context (useMessages) because they change on every
   * typed frame; keeping them out of this one stops the sidebar, top bar,
   * composer and overlays from re-rendering 60 times a second while an answer
   * is being written.
   */
  hasMessages: boolean;
  loadingConversation: boolean;
  /** True while an answer is generating or still being typed out. */
  streaming: boolean;
  /** Every document; use scopedDocuments for the ones the current view (project or general library) holds. */
  documents: DocumentInfo[];
  scopedDocuments: DocumentInfo[];
  projects: Project[];
  /** The project being viewed, or the open conversation's project; null for the general space. */
  activeProjectId: string | null;
  activeProject: Project | null;
  toasts: Toast[];
  needsApiKey: boolean;
  typingSpeed: TypingSpeed;
  modelPickerOpen: boolean;
  memoryPanelOpen: boolean;
  connectionsOpen: boolean;
  /** An answer in the open conversation is paused, waiting for the user to approve an action. */
  awaitingApproval: boolean;
}

export type Decision = 'approve' | 'decline';

interface ChatActions {
  send: (text: string, attachments?: Attachment[], mode?: ChatMode) => Promise<void>;
  regenerate: () => Promise<void>;
  /** Stops generation; if the answer is already complete, shows the rest of it at once. */
  stop: () => void;
  newChat: () => void;
  open: (id: string) => Promise<void>;
  rename: (id: string, title: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  searchConversations: (q: string) => Promise<void>;
  refreshDocuments: () => Promise<void>;
  upload: (files: File[]) => Promise<UploadResponse | null>;
  removeDocument: (id: string) => Promise<void>;
  clearDocuments: () => Promise<void>;
  exportConversation: (id: string) => Promise<void>;
  toast: (text: string, kind?: Toast['kind']) => void;
  dismissToast: (id: string) => void;
  submitApiKey: (key: string) => Promise<void>;
  refreshMeta: () => Promise<void>;
  setTypingSpeed: (speed: TypingSpeed) => void;
  setModelPickerOpen: (open: boolean) => void;
  setMemoryPanelOpen: (open: boolean) => void;
  setConnectionsOpen: (open: boolean) => void;
  openProject: (id: string) => void;
  createProject: (name: string, instructions?: string) => Promise<Project | null>;
  updateProject: (id: string, patch: { name?: string; instructions?: string }) => Promise<boolean>;
  deleteProject: (id: string) => Promise<void>;
  refreshProjects: () => Promise<void>;
  /** Approve or decline the actions a paused answer waits on; the rest of the answer streams into it. */
  approve: (messageId: string, decisions: Record<string, Decision>, alwaysAllow?: string[]) => Promise<void>;
  /** Download one answer of the open conversation as a PDF. */
  exportPdf: (messageId: string) => Promise<void>;
}

const Ctx = createContext<(ChatState & ChatActions) | null>(null);
const MessagesCtx = createContext<UIMessage[] | null>(null);

/** What a paused answer looks like after the user sent a new message instead of approving it. */
function dropPending(m: UIMessage): UIMessage {
  return {
    ...m,
    pendingApproval: undefined,
    approvals: [
      ...(m.approvals ?? []),
      ...(m.pendingApproval ?? []).map((a): ApprovalRecord => ({ id: a.id, tool: a.tool, title: a.title, server: a.server, args: a.args, decision: 'dropped' })),
    ],
    steps: m.steps.map((s) => (s.status === 'waiting' ? { ...s, status: 'declined', result: 'Not approved' } : s)),
  };
}

function readHash(): string | null {
  const m = /^#\/c\/([A-Za-z0-9_\-:.]+)$/.exec(window.location.hash);
  return m ? m[1] : null;
}

function readProjectHash(): string | null {
  const m = /^#\/p\/([A-Za-z0-9_\-]+)$/.exec(window.location.hash);
  return m ? m[1] : null;
}

/** #/c/<conversation>, #/p/<project>, or nothing for the home page. */
function writeHash(id: string | null, kind: 'c' | 'p' = 'c') {
  const target = id ? `#/${kind}/${id}` : window.location.pathname + window.location.search;
  const changed = id ? window.location.hash !== target : window.location.hash !== '';
  if (changed) history.replaceState(null, '', target);
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [serverDown, setServerDown] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationsLoaded, setConversationsLoaded] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const projectRef = useRef<string | null>(null);
  projectRef.current = activeProjectId;
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [needsApiKey, setNeedsApiKey] = useState(false);
  const [typingSpeed, setTypingSpeedState] = useState<TypingSpeed>(readTypingSpeed);
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [memoryPanelOpen, setMemoryPanelOpen] = useState(false);
  const [connectionsOpen, setConnectionsOpen] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const typerRef = useRef<Typewriter | null>(null);
  const activeRef = useRef<string | null>(null);
  activeRef.current = activeId;
  // Read by the typewriter every frame, so a new speed applies to the answer being typed.
  const speedRef = useRef<TypingSpeed>(typingSpeed);
  speedRef.current = typingSpeed;

  const setTypingSpeed = useCallback((speed: TypingSpeed) => {
    setTypingSpeedState(speed);
    saveTypingSpeed(speed);
  }, []);

  // ── toasts ────────────────────────────────────────────────────────────────
  const dismissToast = useCallback((id: string) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const toast = useCallback(
    (text: string, kind: Toast['kind'] = 'info') => {
      const id = uid('toast');
      setToasts((t) => [...t.slice(-3), { id, kind, text }]);
      window.setTimeout(() => dismissToast(id), kind === 'error' ? 7000 : 4000);
    },
    [dismissToast],
  );

  const handleError = useCallback(
    (err: unknown, fallback: string) => {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setNeedsApiKey(true);
          return;
        }
        if (err.code === 'NETWORK') setServerDown(true);
        toast(err.message || fallback, 'error');
      } else {
        toast(fallback, 'error');
      }
    },
    [toast],
  );

  // ── bootstrap ─────────────────────────────────────────────────────────────
  const refreshMeta = useCallback(async () => {
    try {
      const next = await api.meta();
      // Keep the same object when nothing changed, so re-checks don't re-render the app.
      setMeta((prev) => (prev && JSON.stringify(prev) === JSON.stringify(next) ? prev : next));
      setServerDown(false);
    } catch (err) {
      if (err instanceof ApiError && err.code === 'NETWORK') setServerDown(true);
    }
  }, []);

  const loadConversations = useCallback(
    async (q?: string) => {
      try {
        setConversations(await api.conversations(q));
        setConversationsLoaded(true);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) setNeedsApiKey(true);
        else if (err instanceof ApiError && err.code === 'NETWORK') setServerDown(true);
      }
    },
    [],
  );

  const refreshDocuments = useCallback(async () => {
    try {
      setDocuments(await api.documents());
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setNeedsApiKey(true);
    }
  }, []);

  const refreshProjects = useCallback(async () => {
    try {
      setProjects(await api.projects());
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setNeedsApiKey(true);
    }
  }, []);

  const open = useCallback(
    async (id: string) => {
      if (abortRef.current) abortRef.current.abort();
      typerRef.current?.dispose();
      setActiveId(id);
      writeHash(id);
      setLoadingConversation(true);
      try {
        const data = await api.conversation(id);
        if (activeRef.current === id) {
          setMessages(data.messages.map(fromStored));
          setActiveProjectId(data.conversation.project_id ?? null);
        }
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          toast("That conversation doesn't exist anymore.", 'error');
          setActiveId(null);
          setMessages([]);
          writeHash(null);
        } else handleError(err, "Couldn't open the conversation.");
      } finally {
        setLoadingConversation(false);
      }
    },
    [handleError, toast],
  );

  useEffect(() => {
    refreshMeta();
    loadConversations();
    refreshDocuments();
    refreshProjects();
    const initial = readHash();
    if (initial) open(initial);
    const initialProject = readProjectHash();
    if (initialProject) setActiveProjectId(initialProject);
    const onHash = () => {
      const id = readHash();
      if (id && id !== activeRef.current) open(id);
      const pid = readProjectHash();
      if (pid) {
        setActiveId(null);
        setMessages([]);
        setActiveProjectId(pid);
      }
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Retry the connection every few seconds while the server is unreachable.
  useEffect(() => {
    if (!serverDown) return;
    const t = window.setInterval(() => {
      refreshMeta();
      loadConversations();
    }, 5000);
    return () => window.clearInterval(t);
  }, [serverDown, refreshMeta, loadConversations]);

  // The server picks up .env changes without a restart, so re-check the model
  // whenever the tab comes back into view, and every few seconds while it isn't
  // configured. The "not configured" banner then clears on its own once fixed.
  const modelMissing = !!meta && !meta.llm_ready && !serverDown;
  useEffect(() => {
    const recheck = () => {
      if (document.visibilityState === 'visible') void refreshMeta();
    };
    window.addEventListener('focus', recheck);
    document.addEventListener('visibilitychange', recheck);
    const t = modelMissing ? window.setInterval(recheck, 4000) : undefined;
    return () => {
      window.removeEventListener('focus', recheck);
      document.removeEventListener('visibilitychange', recheck);
      if (t) window.clearInterval(t);
    };
  }, [modelMissing, refreshMeta]);

  // ── streaming ─────────────────────────────────────────────────────────────
  const patch = useCallback((id: string, fn: (m: UIMessage) => UIMessage) => {
    setMessages((ms) => ms.map((m) => (m.id === id ? fn(m) : m)));
  }, []);

  const runStream = useCallback(
    async (start: (signal: AbortSignal) => AsyncGenerator<StreamEvent>, assistantTempId: string, firstMessage?: string) => {
      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);
      let assistantId = assistantTempId;
      let finalMessage: StoredMessage | null = null;

      // Tokens are queued and typed out at the reader's chosen speed (see lib/typing.ts).
      typerRef.current?.dispose();
      const typer = new Typewriter(
        (text) => patch(assistantId, (m) => ({ ...m, content: m.content + text })),
        () => charsPerSecond(speedRef.current),
      );
      typerRef.current = typer;

      try {
        for await (const ev of start(controller.signal)) {
          switch (ev.type) {
            case 'meta': {
              const prevId = assistantId;
              assistantId = ev.message_id;
              patch(prevId, (m) => ({ ...m, id: ev.message_id }));
              if (ev.user_message_id) {
                setMessages((ms) =>
                  ms.map((m, i) => (i === ms.length - 2 && m.role === 'user' ? { ...m, id: ev.user_message_id! } : m)),
                );
              }
              if (ev.is_new) {
                setActiveId(ev.conversation_id);
                writeHash(ev.conversation_id);
                const now = new Date().toISOString();
                setConversations((cs) => [
                  {
                    id: ev.conversation_id,
                    title: firstMessage?.slice(0, 58) || 'New chat',
                    created_at: now,
                    updated_at: now,
                    message_count: 1,
                    project_id: projectRef.current,
                  },
                  ...cs.filter((c) => c.id !== ev.conversation_id),
                ]);
              }
              break;
            }
            case 'route':
              patch(assistantId, (m) => ({ ...m, route: ev.route, routeReason: ev.reason }));
              break;
            case 'step':
              patch(assistantId, (m) => {
                const steps: Step[] = [...m.steps];
                const i = steps.findIndex((s) => s.id === ev.step.id);
                if (i >= 0) steps[i] = { ...steps[i], ...ev.step };
                else steps.push(ev.step);
                return { ...m, steps };
              });
              break;
            case 'token':
              typer.push(ev.text);
              break;
            case 'draft_reset':
              typer.reset();
              patch(assistantId, (m) => ({ ...m, content: '' }));
              break;
            case 'sources':
              patch(assistantId, (m) => ({ ...m, sources: ev.items }));
              break;
            case 'approval_required':
              patch(assistantId, (m) => ({ ...m, pendingApproval: ev.actions }));
              break;
            case 'title':
              setConversations((cs) => cs.map((c) => (c.id === ev.conversation_id ? { ...c, title: ev.title } : c)));
              break;
            case 'done':
              // Applied once the typing has caught up, so the answer doesn't jump to the end.
              finalMessage = ev.message;
              break;
            case 'error':
              typer.finish();
              patch(assistantId, (m) => ({ ...m, status: 'error', error: ev.message }));
              break;
          }
        }

        // The server is finished; let the typing catch up (Stop skips to the end).
        await typer.drain();

        if (finalMessage) {
          if (projectRef.current) void refreshProjects();
          const stored = fromStored(finalMessage);
          patch(assistantId, (m) => ({ ...stored, steps: stored.steps.length ? stored.steps : m.steps }));
          const convId = finalMessage.conversation_id;
          setConversations((cs) => {
            const c = cs.find((x) => x.id === convId);
            if (!c) return cs;
            const updated = {
              ...c,
              updated_at: new Date().toISOString(),
              message_count: c.message_count + 1,
              last_route: stored.route ?? c.last_route,
            };
            return [updated, ...cs.filter((x) => x.id !== convId)];
          });
        } else {
          // Stream ended without "done" (stopped or dropped).
          patch(assistantId, (m) =>
            m.status === 'streaming'
              ? {
                  ...m,
                  status: controller.signal.aborted ? 'stopped' : 'error',
                  error: controller.signal.aborted ? undefined : 'The answer was cut off.',
                }
              : m,
          );
        }
      } catch (err) {
        typer.finish();
        if (err instanceof ApiError && err.status === 401) {
          setNeedsApiKey(true);
          setMessages((ms) => ms.filter((m) => m.id !== assistantId));
        } else {
          const message = err instanceof Error ? err.message : 'Something went wrong.';
          patch(assistantId, (m) => ({ ...m, status: 'error', error: message }));
          if (err instanceof ApiError && err.code === 'NETWORK') setServerDown(true);
        }
      } finally {
        typer.dispose();
        if (typerRef.current === typer) typerRef.current = null;
        if (abortRef.current === controller) abortRef.current = null;
        setStreaming(false);
      }
    },
    [patch, refreshProjects],
  );

  const send = useCallback(
    async (text: string, attachments: Attachment[] = [], mode: ChatMode = 'auto') => {
      const message = text.trim();
      if (!message || abortRef.current) return;
      const now = new Date().toISOString();
      const assistantTempId = uid('pending');
      setMessages((ms) => [
        // A new message on a paused answer counts as not approving it (the server records the same).
        ...ms.map((m) => (m.pendingApproval ? dropPending(m) : m)),
        { id: uid('user'), role: 'user', content: message, createdAt: now, steps: [], sources: [], attachments, mode, status: 'done' },
        { id: assistantTempId, role: 'assistant', content: '', createdAt: now, steps: [], sources: [], status: 'streaming' },
      ]);
      const body = { message, conversation_id: activeRef.current, attachments, mode, project_id: projectRef.current };
      await runStream((signal) => streamChat(body, signal), assistantTempId, message);
    },
    [runStream],
  );

  const regenerate = useCallback(async () => {
    const id = activeRef.current;
    if (!id || abortRef.current) return;
    const assistantTempId = uid('pending');
    setMessages((ms) => {
      const trimmed = ms[ms.length - 1]?.role === 'assistant' ? ms.slice(0, -1) : ms;
      return [
        ...trimmed,
        { id: assistantTempId, role: 'assistant', content: '', createdAt: new Date().toISOString(), steps: [], sources: [], status: 'streaming' },
      ];
    });
    await runStream((signal) => streamChat({ conversation_id: id, regenerate: true }, signal), assistantTempId);
  }, [runStream]);

  const approve = useCallback(
    async (messageId: string, decisions: Record<string, Decision>, alwaysAllow: string[] = []) => {
      const conversationId = activeRef.current;
      if (!conversationId || abortRef.current) return;
      patch(messageId, (m) => ({
        ...m,
        status: 'streaming',
        pendingApproval: undefined,
        approvals: [
          ...(m.approvals ?? []),
          ...(m.pendingApproval ?? []).map(
            (a): ApprovalRecord => ({ id: a.id, tool: a.tool, title: a.title, server: a.server, args: a.args, decision: decisions[a.id] ?? 'decline' }),
          ),
        ],
      }));
      const body = { conversation_id: conversationId, message_id: messageId, decisions, always_allow: alwaysAllow };
      await runStream((signal) => streamApproval(body, signal), messageId);
    },
    [patch, runStream],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    typerRef.current?.finish();
  }, []);

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    typerRef.current?.dispose();
    setActiveId(null);
    setMessages([]);
    setActiveProjectId(null);
    writeHash(null);
  }, []);

  // ── projects ──────────────────────────────────────────────────────────────
  const openProject = useCallback((id: string) => {
    abortRef.current?.abort();
    typerRef.current?.dispose();
    setActiveId(null);
    setMessages([]);
    setActiveProjectId(id);
    writeHash(id, 'p');
  }, []);

  const createProject = useCallback(
    async (name: string, instructions = '') => {
      try {
        const project = await api.createProject(name, instructions);
        setProjects((ps) => [project, ...ps]);
        openProject(project.id);
        return project;
      } catch (err) {
        handleError(err, "Couldn't create the project.");
        return null;
      }
    },
    [handleError, openProject],
  );

  const updateProject = useCallback(
    async (id: string, patch: { name?: string; instructions?: string }) => {
      try {
        const project = await api.updateProject(id, patch);
        setProjects((ps) => ps.map((p) => (p.id === id ? project : p)));
        return true;
      } catch (err) {
        handleError(err, "Couldn't save the project.");
        return false;
      }
    },
    [handleError],
  );

  const deleteProject = useCallback(
    async (id: string) => {
      try {
        const res = await api.deleteProject(id);
        setProjects((ps) => ps.filter((p) => p.id !== id));
        setConversations((cs) => cs.filter((c) => c.project_id !== id));
        setDocuments((ds) => ds.filter((d) => d.project_id !== id));
        if (projectRef.current === id) newChat();
        toast(`Deleted the project with ${res.chats} ${res.chats === 1 ? 'chat' : 'chats'} and ${res.documents} ${res.documents === 1 ? 'file' : 'files'}.`, 'success');
      } catch (err) {
        handleError(err, "Couldn't delete the project.");
      }
    },
    [handleError, newChat, toast],
  );

  // ── conversation management ──────────────────────────────────────────────
  const rename = useCallback(
    async (id: string, title: string) => {
      const prev = conversations;
      setConversations((cs) => cs.map((c) => (c.id === id ? { ...c, title } : c)));
      try {
        await api.rename(id, title);
      } catch (err) {
        setConversations(prev);
        handleError(err, "Couldn't rename the conversation.");
      }
    },
    [conversations, handleError],
  );

  const remove = useCallback(
    async (id: string) => {
      const prev = conversations;
      setConversations((cs) => cs.filter((c) => c.id !== id));
      if (activeRef.current === id) newChat();
      try {
        await api.remove(id);
        toast('Conversation deleted.', 'success');
      } catch (err) {
        setConversations(prev);
        handleError(err, "Couldn't delete the conversation.");
      }
    },
    [conversations, handleError, newChat, toast],
  );

  const searchConversations = useCallback((q: string) => loadConversations(q || undefined), [loadConversations]);

  const exportConversation = useCallback(
    async (id: string) => {
      try {
        const { filename, text } = await api.exportMarkdown(id);
        const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown' }));
        const a = Object.assign(document.createElement('a'), { href: url, download: filename });
        a.click();
        URL.revokeObjectURL(url);
      } catch (err) {
        handleError(err, "Couldn't export the conversation.");
      }
    },
    [handleError],
  );

  const exportPdf = useCallback(
    async (messageId: string) => {
      const conversationId = activeRef.current;
      if (!conversationId) return;
      try {
        const { filename, blob } = await api.exportPdf(conversationId, messageId);
        const url = URL.createObjectURL(blob);
        const a = Object.assign(document.createElement('a'), { href: url, download: filename });
        a.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 2000);
      } catch (err) {
        handleError(err, "Couldn't create the PDF.");
      }
    },
    [handleError],
  );

  // ── documents ─────────────────────────────────────────────────────────────
  const upload = useCallback(
    async (files: File[]) => {
      try {
        const res = await api.upload(files, projectRef.current);
        await refreshDocuments();
        refreshMeta();
        if (projectRef.current) void refreshProjects();
        const failed = res.results.filter((r) => r.status === 'error');
        if (res.documents_added) {
          toast(`Added ${res.documents_added} ${res.documents_added === 1 ? 'document' : 'documents'} to your library.`, 'success');
        }
        failed.forEach((f) => toast(f.error || `Couldn't add ${f.name}.`, 'error'));
        return res;
      } catch (err) {
        handleError(err, "Couldn't upload the files.");
        return null;
      }
    },
    [handleError, refreshDocuments, refreshMeta, refreshProjects, toast],
  );

  const removeDocument = useCallback(
    async (id: string) => {
      const prev = documents;
      setDocuments((ds) => ds.filter((d) => d.id !== id));
      try {
        await api.removeDocument(id);
        refreshMeta();
      } catch (err) {
        setDocuments(prev);
        handleError(err, "Couldn't remove the document.");
      }
    },
    [documents, handleError, refreshMeta],
  );

  const clearDocuments = useCallback(async () => {
    try {
      const { deleted } = await api.clearDocuments();
      setDocuments([]);
      refreshMeta();
      toast(`Removed ${deleted} ${deleted === 1 ? 'document' : 'documents'}.`, 'success');
    } catch (err) {
      handleError(err, "Couldn't clear the library.");
    }
  }, [handleError, refreshMeta, toast]);

  const submitApiKey = useCallback(
    async (key: string) => {
      persistApiKey(key.trim() || null);
      setNeedsApiKey(false);
      await Promise.all([refreshMeta(), loadConversations(), refreshDocuments()]);
    },
    [loadConversations, refreshDocuments, refreshMeta],
  );

  const hasMessages = messages.length > 0;
  const scopedDocuments = useMemo(
    () => documents.filter((d) => (d.project_id ?? null) === activeProjectId),
    [documents, activeProjectId],
  );
  const activeProject = useMemo(() => projects.find((p) => p.id === activeProjectId) ?? null, [projects, activeProjectId]);
  const awaitingApproval = messages.some((m) => !!m.pendingApproval?.length);
  const value = useMemo(
    () => ({
      meta, serverDown, conversations, conversationsLoaded, activeId, hasMessages, loadingConversation, streaming,
      documents, scopedDocuments, projects, activeProjectId, activeProject, toasts, needsApiKey, typingSpeed,
      modelPickerOpen, memoryPanelOpen, connectionsOpen, awaitingApproval,
      send, regenerate, stop, newChat, open, rename, remove, searchConversations, refreshDocuments, upload,
      removeDocument, clearDocuments, exportConversation, toast, dismissToast, submitApiKey, refreshMeta,
      setTypingSpeed, setModelPickerOpen, setMemoryPanelOpen, setConnectionsOpen, approve, exportPdf,
      openProject, createProject, updateProject, deleteProject, refreshProjects,
    }),
    [
      meta, serverDown, conversations, conversationsLoaded, activeId, hasMessages, loadingConversation, streaming,
      documents, scopedDocuments, projects, activeProjectId, activeProject, toasts, needsApiKey, typingSpeed,
      modelPickerOpen, memoryPanelOpen, connectionsOpen, awaitingApproval,
      send, regenerate, stop, newChat, open, rename, remove, searchConversations, refreshDocuments, upload,
      removeDocument, clearDocuments, exportConversation, toast, dismissToast, submitApiKey, refreshMeta, setTypingSpeed,
      approve, exportPdf, openProject, createProject, updateProject, deleteProject, refreshProjects,
    ],
  );

  return (
    <Ctx.Provider value={value}>
      <MessagesCtx.Provider value={messages}>{children}</MessagesCtx.Provider>
    </Ctx.Provider>
  );
}

export function useChat() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useChat must be used inside <ChatProvider>');
  return ctx;
}

/** Messages of the open conversation. Changes on every typed frame, so only the message list should use it. */
export function useMessages() {
  const messages = useContext(MessagesCtx);
  if (!messages) throw new Error('useMessages must be used inside <ChatProvider>');
  return messages;
}
