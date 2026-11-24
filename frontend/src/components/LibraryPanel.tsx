import { useEffect, useRef, useState, type DragEvent } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { FileText, Loader2, Trash2, Upload, X } from 'lucide-react';
import { useChat } from '@/lib/chat-store';
import { cn, formatBytes } from '@/lib/utils';

async function filesFromDrop(e: DragEvent): Promise<File[]> {
  const out: File[] = [];
  const entries = Array.from(e.dataTransfer.items ?? [])
    .map((i) => i.webkitGetAsEntry?.())
    .filter(Boolean) as FileSystemEntry[];
  if (!entries.length) return Array.from(e.dataTransfer.files);

  const walk = async (entry: FileSystemEntry): Promise<void> => {
    if (entry.isFile) {
      out.push(await new Promise<File>((res, rej) => (entry as FileSystemFileEntry).file(res, rej)));
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      let batch: FileSystemEntry[];
      do {
        batch = await new Promise<FileSystemEntry[]>((res, rej) => reader.readEntries(res, rej));
        for (const child of batch) await walk(child);
      } while (batch.length);
    }
  };
  for (const entry of entries) await walk(entry);
  return out;
}

export function LibraryPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { documents, upload, removeDocument, clearDocuments, refreshDocuments, meta } = useChat();
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) {
      void refreshDocuments();
      closeRef.current?.focus();
    } else setConfirmClear(false);
  }, [open, refreshDocuments]);

  const add = async (files: File[]) => {
    if (!files.length) return;
    setBusy(true);
    await upload(files);
    setBusy(false);
  };

  const totalChunks = documents.reduce((n, d) => n + d.chunks, 0);
  const persistent = meta?.knowledge_base.backend === 'pgvector';

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
            aria-labelledby="library-title"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 380, damping: 38 }}
            onKeyDown={(e) => e.key === 'Escape' && onClose()}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[420px] flex-col border-l border-line bg-bg shadow-lift"
          >
            <div className="flex items-start justify-between gap-4 px-5 pb-2 pt-5">
              <div>
                <h2 id="library-title" className="text-[19px] font-[780] tracking-[-0.01em] text-ink">
                  Document library
                </h2>
                <p className="mt-1 text-[14px] leading-relaxed text-muted">
                  Ask about anything in these files from any conversation. Answers cite the passages they use.
                </p>
              </div>
              <button ref={closeRef} type="button" onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-raised hover:text-ink" aria-label="Close library">
                <X className="size-4" />
              </button>
            </div>

            <div className="px-5 pt-3">
              <input
                ref={fileRef}
                type="file"
                multiple
                className="hidden"
                onChange={(e) => {
                  void add(Array.from(e.target.files ?? []));
                  e.target.value = '';
                }}
              />
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={async (e) => {
                  e.preventDefault();
                  setDragging(false);
                  void add(await filesFromDrop(e));
                }}
                disabled={busy}
                className={cn(
                  'flex w-full flex-col items-center gap-2 rounded-2xl border-2 border-dashed px-4 py-7 text-center transition-colors',
                  dragging ? 'border-route-docs bg-route-docs/10' : 'border-line hover:border-line-strong',
                )}
              >
                {busy ? <Loader2 className="size-6 animate-spin text-route-docs" /> : <Upload className="size-6 text-route-docs" />}
                <span className="text-[14.5px] font-semibold text-ink">{busy ? 'Reading and indexing' : 'Add files or drop a folder'}</span>
                <span className="text-[12.5px] text-muted">
                  PDF, text, Markdown, CSV, JSON and code, up to {meta?.limits.max_upload_mb ?? 25} MB each
                </span>
              </button>
              {meta && !persistent && (
                <p className="mt-2 text-[12.5px] leading-snug text-faint">
                  The library isn't connected to a database right now, so documents are kept in memory and clear when the server restarts.
                </p>
              )}
            </div>

            <div className="scroll-quiet mt-4 min-h-0 flex-1 overflow-y-auto px-3 pb-3">
              {documents.length === 0 ? (
                <p className="px-2 py-6 text-[14px] text-muted">Nothing here yet. Files you attach in a chat also land here.</p>
              ) : (
                <ul className="space-y-1">
                  {documents.map((d) => (
                    <li key={d.id} className="group flex items-center gap-3 rounded-xl px-2 py-2 hover:bg-raised">
                      <FileText className="size-4 shrink-0 text-route-docs" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[14px] text-ink" title={d.name}>
                          {d.name}
                        </p>
                        <p className="text-[12.5px] text-faint">
                          {formatBytes(d.size_bytes)}, {d.chunks} {d.chunks === 1 ? 'passage' : 'passages'}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => void removeDocument(d.id)}
                        className="rounded-lg p-1.5 text-faint opacity-100 hover:text-danger sm:opacity-0 sm:group-hover:opacity-100 sm:focus:opacity-100"
                        aria-label={`Remove ${d.name}`}
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {documents.length > 0 && (
              <div className="flex items-center justify-between border-t border-line px-5 py-3 text-[13px]">
                <span className="text-faint">
                  {documents.length} {documents.length === 1 ? 'file' : 'files'}, {totalChunks} {totalChunks === 1 ? 'passage' : 'passages'}
                </span>
                {confirmClear ? (
                  <span className="flex items-center gap-2">
                    <button type="button" onClick={() => { void clearDocuments(); setConfirmClear(false); }} className="rounded-lg px-2.5 py-1 font-semibold text-danger hover:bg-danger/10">
                      Remove all
                    </button>
                    <button type="button" onClick={() => setConfirmClear(false)} className="rounded-lg px-2.5 py-1 text-muted hover:text-ink">
                      Keep
                    </button>
                  </span>
                ) : (
                  <button type="button" onClick={() => setConfirmClear(true)} className="rounded-lg px-2.5 py-1 text-muted hover:text-danger">
                    Remove all
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
