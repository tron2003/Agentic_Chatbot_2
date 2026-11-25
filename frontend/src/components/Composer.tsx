import { forwardRef, memo, useCallback, useImperativeHandle, useRef, useState, type DragEvent, type KeyboardEvent } from 'react';
import { ArrowUp, CircleAlert, CircleCheck, Loader2, Paperclip, Square, Upload, X } from 'lucide-react';
import { useChat } from '@/lib/chat-store';
import type { Attachment } from '@/lib/types';
import { cn } from '@/lib/utils';

const ACCEPT =
  '.pdf,.txt,.md,.markdown,.csv,.tsv,.json,.jsonl,.xml,.yaml,.yml,.toml,.log,.sql,.html,.css,.py,.js,.ts,.jsx,.tsx,.java,.go,.rs,.c,.cpp,.h,.rb,.php,.sh';

interface Pending {
  key: string;
  name: string;
  status: 'uploading' | 'ok' | 'error';
  doc?: Attachment;
  error?: string;
}

export interface ComposerHandle {
  focus: () => void;
  setText: (text: string) => void;
}

// memo: the composer sits inside the message list's parent, which re-renders on
// every typed frame of an answer. Its props never change, so it can skip those.
export const Composer = memo(
  forwardRef<ComposerHandle, { placeholder?: string; autoFocus?: boolean }>(function Composer(
    { placeholder = 'Ask a question', autoFocus },
    ref,
  ) {
    const { send, stop, streaming, upload, meta, serverDown } = useChat();
    const [text, setText] = useState('');
    const [files, setFiles] = useState<Pending[]>([]);
    const [dragging, setDragging] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const fileRef = useRef<HTMLInputElement>(null);
    // dragenter/dragleave fire for every child element; count them so the drop
    // highlight doesn't flicker as the pointer crosses the textarea and buttons.
    const dragDepth = useRef(0);
    const maxChars = meta?.limits.max_message_chars ?? 16000;

    const resize = () => {
      const el = textareaRef.current;
      if (!el) return;
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
    };

    useImperativeHandle(ref, () => ({
      focus: () => textareaRef.current?.focus(),
      setText: (t: string) => {
        setText(t);
        requestAnimationFrame(() => {
          resize();
          const el = textareaRef.current;
          if (el) {
            el.focus();
            el.setSelectionRange(t.length, t.length);
          }
        });
      },
    }));

    const addFiles = useCallback(
      async (list: File[]) => {
        if (!list.length) return;
        const batch: Pending[] = list.map((f, i) => ({ key: `${Date.now()}-${i}-${f.name}`, name: f.name, status: 'uploading' }));
        setFiles((prev) => [...prev, ...batch]);
        const res = await upload(list);
        setFiles((prev) =>
          prev.map((p) => {
            const idx = batch.findIndex((b) => b.key === p.key);
            if (idx === -1) return p;
            const r = res?.results[idx];
            if (r?.status === 'ok' && r.document) return { ...p, status: 'ok', doc: { id: r.document.id, name: r.document.name } };
            return { ...p, status: 'error', error: r?.error ?? 'Upload failed' };
          }),
        );
        textareaRef.current?.focus();
      },
      [upload],
    );

    const uploading = files.some((f) => f.status === 'uploading');
    const ready = files.filter((f) => f.status === 'ok' && f.doc).map((f) => f.doc!);
    const tooLong = text.length > maxChars;
    const canSend = !!text.trim() && !streaming && !uploading && !tooLong && !serverDown;

    const submit = () => {
      if (!canSend) return;
      const message = text;
      setText('');
      setFiles([]);
      requestAnimationFrame(resize);
      void send(message, ready);
    };

    const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
        e.preventDefault();
        submit();
      }
    };

    const hasFiles = (e: DragEvent) => e.dataTransfer.types.includes('Files');

    return (
      <div
        onDragEnter={(e) => {
          if (!hasFiles(e)) return;
          e.preventDefault();
          dragDepth.current += 1;
          setDragging(true);
        }}
        onDragOver={(e) => {
          if (hasFiles(e)) e.preventDefault();
        }}
        onDragLeave={() => {
          dragDepth.current = Math.max(0, dragDepth.current - 1);
          if (dragDepth.current === 0) setDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          void addFiles(Array.from(e.dataTransfer.files));
        }}
        className={cn(
          'glass relative rounded-[22px] border border-line shadow-lift transition-[border-color,box-shadow] duration-200 focus-within:border-line-strong',
          dragging && 'border-accent ring-4 ring-accent/15',
        )}
      >
        {dragging && (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center gap-2 rounded-[22px] bg-raised/85 text-[14px] font-semibold text-accent">
            <Upload className="size-4" /> Drop files to add them to your library
          </div>
        )}

        {files.length > 0 && (
          <ul className="flex flex-wrap gap-1.5 px-3 pt-3" aria-label="Attached files">
            {files.map((f) => (
              <li
                key={f.key}
                title={f.status === 'error' ? f.error : f.status === 'uploading' ? 'Adding to your library…' : 'Added to your library'}
                className={cn(
                  'animate-chip-in inline-flex max-w-[16rem] items-center gap-1.5 rounded-lg border px-2 py-1 text-[12.5px] transition-colors',
                  f.status === 'error' && 'border-danger/50 bg-danger/10 text-danger',
                  f.status === 'uploading' && 'border-line bg-raised text-muted',
                  f.status === 'ok' && 'border-route-agent/40 bg-raised text-ink',
                )}
              >
                {f.status === 'uploading' ? (
                  <Loader2 className="size-3.5 shrink-0 animate-spin" />
                ) : f.status === 'ok' ? (
                  <CircleCheck className="size-3.5 shrink-0 text-route-agent" />
                ) : (
                  <CircleAlert className="size-3.5 shrink-0" />
                )}
                <span className="truncate">{f.name}</span>
                <button
                  type="button"
                  onClick={() => setFiles((prev) => prev.filter((p) => p.key !== f.key))}
                  className="rounded p-0.5 text-faint transition-colors hover:bg-sunk hover:text-ink"
                  aria-label={`Remove ${f.name}`}
                >
                  <X className="size-3" />
                </button>
              </li>
            ))}
          </ul>
        )}

        <label htmlFor="composer-input" className="sr-only">
          Message
        </label>
        <textarea
          id="composer-input"
          ref={textareaRef}
          value={text}
          autoFocus={autoFocus}
          rows={1}
          onChange={(e) => {
            setText(e.target.value);
            resize();
          }}
          onKeyDown={onKeyDown}
          placeholder={serverDown ? 'Waiting for the server…' : placeholder}
          className="block max-h-60 min-h-[56px] w-full resize-none bg-transparent px-4 pt-4 pb-2 text-[15.5px] leading-relaxed text-ink outline-none placeholder:text-faint"
        />

        <div className="flex items-center justify-between gap-2 px-2.5 pb-2.5">
          <div className="flex items-center gap-2">
            <input
              ref={fileRef}
              type="file"
              multiple
              accept={ACCEPT}
              className="hidden"
              onChange={(e) => {
                void addFiles(Array.from(e.target.files ?? []));
                e.target.value = '';
              }}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className={cn(
                'group/attach inline-flex items-center gap-1.5 rounded-xl border px-2.5 py-1.5 text-[13px] font-medium',
                'transition-[background-color,border-color,color,transform] duration-150 ease-out',
                'hover:-translate-y-px hover:border-line-strong hover:bg-raised hover:text-ink hover:shadow-lift',
                'active:translate-y-0 active:scale-[0.96] active:bg-sunk',
                uploading ? 'border-line-strong bg-raised text-ink' : 'border-line bg-raised/60 text-muted',
              )}
              aria-label="Attach files to your document library"
              title="Attach files. They're added to your document library so you can ask about them. You can also drop files here."
            >
              {uploading ? (
                <Loader2 className="size-4 animate-spin text-route-docs" />
              ) : (
                <Paperclip className="size-4 transition-transform duration-200 group-hover/attach:-rotate-12 group-hover/attach:text-route-docs" />
              )}
              <span className="hidden sm:inline">{uploading ? 'Uploading…' : 'Attach'}</span>
              {ready.length > 0 && !uploading && (
                <span className="rounded-full bg-route-docs/15 px-1.5 text-[11.5px] font-semibold text-route-docs">{ready.length}</span>
              )}
            </button>
            {tooLong && (
              <span className="text-[12px] text-danger">
                {text.length.toLocaleString()} / {maxChars.toLocaleString()} characters
              </span>
            )}
          </div>

          {streaming ? (
            <button
              type="button"
              onClick={stop}
              className="inline-flex size-10 items-center justify-center rounded-full border border-line-strong bg-raised text-ink transition-[background-color,transform] duration-150 hover:bg-sunk active:scale-90"
              aria-label="Stop generating"
              title="Stop generating (Esc)"
            >
              <Square className="size-3.5 fill-current" />
            </button>
          ) : (
            <button
              type="button"
              onClick={submit}
              disabled={!canSend}
              className="inline-flex size-10 items-center justify-center rounded-full bg-accent text-accent-ink transition-[opacity,transform] duration-150 hover:scale-105 active:scale-90 disabled:scale-100 disabled:opacity-35"
              aria-label="Send message"
              title="Send (Enter). Shift + Enter adds a new line."
            >
              {uploading ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-[18px]" strokeWidth={2.5} />}
            </button>
          )}
        </div>
      </div>
    );
  }),
);
