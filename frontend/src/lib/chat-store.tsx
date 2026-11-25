import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, ApiError, setApiKey as persistApiKey, streamChat, type ChatBody } from './api';
import type { Attachment, Conversation, DocumentInfo, Meta, Step, StoredMessage, UIMessage, UploadResponse } from './types';
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
  documents: DocumentInfo[];
  toasts: Toast[];
  needsApiKey: boolean;
  typingSpeed: TypingSpeed;
}

interface ChatActions {
  send: (text: string, attachments?: Attachment[]) => Promise<void>;
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
}

const Ctx = createContext<(ChatState & ChatActions) | null>(null);
const MessagesCtx = createContext<UIMessage[] | null>(null);

function readHash(): string | null {
  const m = /^#\/c\/([A-Za-z0-9_\-:.]+)$/.exec(window.location.hash);
  return m ? m[1] : null;
}

function writeHash(id: string | null) {
  const target = id ? `#/c/${id}` : window.location.pathname + window.location.search;
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
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [needsApiKey, setNeedsApiKey] = useState(false);
  const [typingSpeed, setTypingSpeedState] = useState<TypingSpeed>(readTypingSpeed);

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

  const open = useCallback(
    async (id: string) => {
      if (abortRef.current) abortRef.current.abort();
      typerRef.current?.dispose();
      setActiveId(id);
      writeHash(id);
      setLoadingConversation(true);
      try {
        const data = await api.conversation(id);
        if (activeRef.current === id) setMessages(data.messages.map(fromStored));
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
    const initial = readHash();
    if (initial) open(initial);
    const onHash = () => {
      const id = readHash();
      if (id && id !== activeRef.current) open(id);
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
    async (body: ChatBody, assistantTempId: string) => {
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
        for await (const ev of streamChat(body, controller.signal)) {
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
                    title: body.message?.slice(0, 58) || 'New chat',
                    created_at: now,
                    updated_at: now,
                    message_count: 1,
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
          const stored = fromStored(finalMessage);
          patch(assistantId, (m) => ({ ...stored, steps: stored.steps.length ? stored.steps : m.steps }));
          const convId = finalMessage.conversation_id;
          setConversations((cs) => {
            const c = cs.find((x) => x.id === convId);
            if (!c) return cs;
            const updated = { ...c, updated_at: new Date().toISOString(), message_count: c.message_count + 1 };
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
    [patch],
  );

  const send = useCallback(
    async (text: string, attachments: Attachment[] = []) => {
      const message = text.trim();
      if (!message || abortRef.current) return;
      const now = new Date().toISOString();
      const assistantTempId = uid('pending');
      setMessages((ms) => [
        ...ms,
        { id: uid('user'), role: 'user', content: message, createdAt: now, steps: [], sources: [], attachments, status: 'done' },
        { id: assistantTempId, role: 'assistant', content: '', createdAt: now, steps: [], sources: [], status: 'streaming' },
      ]);
      await runStream({ message, conversation_id: activeRef.current, attachments }, assistantTempId);
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
    await runStream({ conversation_id: id, regenerate: true }, assistantTempId);
  }, [runStream]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    typerRef.current?.finish();
  }, []);

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    typerRef.current?.dispose();
    setActiveId(null);
    setMessages([]);
    writeHash(null);
  }, []);

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

  // ── documents ─────────────────────────────────────────────────────────────
  const upload = useCallback(
    async (files: File[]) => {
      try {
        const res = await api.upload(files);
        await refreshDocuments();
        refreshMeta();
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
    [handleError, refreshDocuments, refreshMeta, toast],
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
  const value = useMemo(
    () => ({
      meta, serverDown, conversations, conversationsLoaded, activeId, hasMessages, loadingConversation, streaming,
      documents, toasts, needsApiKey, typingSpeed,
      send, regenerate, stop, newChat, open, rename, remove, searchConversations, refreshDocuments, upload,
      removeDocument, clearDocuments, exportConversation, toast, dismissToast, submitApiKey, refreshMeta,
      setTypingSpeed,
    }),
    [
      meta, serverDown, conversations, conversationsLoaded, activeId, hasMessages, loadingConversation, streaming,
      documents, toasts, needsApiKey, typingSpeed, send, regenerate, stop, newChat, open, rename, remove,
      searchConversations, refreshDocuments, upload, removeDocument, clearDocuments, exportConversation, toast,
      dismissToast, submitApiKey, refreshMeta, setTypingSpeed,
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
