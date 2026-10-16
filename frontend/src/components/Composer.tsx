import { forwardRef, useCallback, useImperativeHandle, useRef, useState, type DragEvent, type KeyboardEvent } from 'react';
import { ArrowUp, Loader2, Paperclip, Square, X } from 'lucide-react';
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

export const Composer = forwardRef<ComposerHandle, { placeholder?: string; autoFocus?: boolean }>(function Composer(
  { placeholder = 'Ask a question', autoFocus },
  ref,
) {
  const { send, stop, streaming, upload, meta, serverDown } = useChat();
  const [text, setText] = useState('');
  const [files, setFiles] = useState<Pending[]>([]);
  const [dragging, setDragging] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
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

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    void addFiles(Array.from(e.dataTransfer.files));
  };

  return (
    <div
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes('Files')) {
          e.preventDefault();
          setDragging(true);
        }
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={cn(
        'glass relative rounded-[22px] border border-line shadow-lift transition-colors focus-within:border-line-strong',
        dragging && 'border-accent',
      )}
    >
      {files.length > 0 && (
        <ul className="flex flex-wrap gap-1.5 px-3 pt-3" aria-label="Attached files">
          {files.map((f) => (
            <li
              key={f.key}
              title={f.error}
              className={cn(
                'inline-flex max-w-[16rem] items-center gap-1.5 rounded-lg border px-2 py-1 text-[12.5px]',
                f.status === 'error' ? 'border-danger/50 text-danger' : 'border-line bg-raised text-ink',
              )}
            >
              {f.status === 'uploading' ? <Loader2 className="size-3.5 animate-spin text-muted" /> : <Paperclip className="size-3.5 text-muted" />}
              <span className="truncate">{f.name}</span>
              <button
                type="button"
                onClick={() => setFiles((prev) => prev.filter((p) => p.key !== f.key))}
                className="rounded p-0.5 text-faint hover:text-ink"
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
        <div className="flex items-center gap-1">
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
            className="inline-flex items-center gap-1.5 rounded-xl px-2.5 py-2 text-[13px] text-muted hover:bg-raised hover:text-ink"
            aria-label="Attach files to your document library"
            title="Attach files. They're added to your document library so you can ask about them."
          >
            <Paperclip className="size-4" />
            <span className="hidden sm:inline">Attach</span>
          </button>
          {tooLong ? (
            <span className="text-[12px] text-danger">{text.length.toLocaleString()} / {maxChars.toLocaleString()} characters</span>
          ) : (
            <span className="hidden text-[12px] text-faint md:inline">
              <span className="kbd">Enter</span> to send, <span className="kbd">Shift</span> + <span className="kbd">Enter</span> for a new line
            </span>
          )}
        </div>

        {streaming ? (
          <button
            type="button"
            onClick={stop}
            className="inline-flex size-10 items-center justify-center rounded-full border border-line-strong bg-raised text-ink hover:bg-sunk"
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
            className="inline-flex size-10 items-center justify-center rounded-full bg-accent text-accent-ink transition-opacity disabled:opacity-35"
            aria-label="Send message"
          >
            {uploading ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-[18px]" strokeWidth={2.5} />}
          </button>
        )}
      </div>
    </div>
  );
});
