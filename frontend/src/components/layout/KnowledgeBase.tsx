import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Database,
  Upload,
  FolderOpen,
  FileText,
  Trash2,
  CheckCircle,
  AlertCircle,
  Loader,
  X,
  ChevronDown,
  ChevronUp,
  Sparkles,
  File as FileIcon,
  HardDrive,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  uploadDocuments,
  getIngestedDocuments,
  clearKnowledgeBase,
  type DocumentInfo,
  type IngestResponse,
} from '@/lib/api';

// ── File type icon helper ────────────────────────────────────────────────────

function getFileTypeColor(fileType: string): string {
  const colors: Record<string, string> = {
    '.pdf': 'text-red-500',
    '.txt': 'text-blue-500',
    '.md': 'text-purple-500',
    '.py': 'text-yellow-500',
    '.js': 'text-yellow-400',
    '.ts': 'text-blue-400',
    '.json': 'text-green-500',
    '.csv': 'text-emerald-500',
    '.html': 'text-orange-500',
    '.css': 'text-blue-300',
  };
  return colors[fileType] || 'text-muted-foreground';
}

// ── Upload State Types ───────────────────────────────────────────────────────

type UploadState = 'idle' | 'uploading' | 'success' | 'error';

interface UploadResult {
  state: UploadState;
  message: string;
  details?: IngestResponse;
}

// ─────────────────────────────────────────────────────────────────────────────

export function KnowledgeBase() {
  const [isExpanded, setIsExpanded] = useState(false);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResult>({
    state: 'idle',
    message: '',
  });
  const [isDragOver, setIsDragOver] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [uploadProgress, setUploadProgress] = useState(0);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  // ── Fetch documents on expand ──────────────────────────────────────────

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const docs = await getIngestedDocuments();
      setDocuments(docs);
    } catch (err) {
      console.error('Failed to fetch documents:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isExpanded) {
      fetchDocuments();
    }
  }, [isExpanded, fetchDocuments]);

  // ── Upload handler ─────────────────────────────────────────────────────

  const handleUpload = useCallback(async (files: File[]) => {
    if (files.length === 0) return;

    setUploadResult({ state: 'uploading', message: `Uploading ${files.length} file(s)…` });
    setUploadProgress(0);
    setPendingFiles(files);

    // Simulate progress (actual upload doesn't give progress via fetch)
    const progressInterval = setInterval(() => {
      setUploadProgress(prev => {
        if (prev >= 90) {
          clearInterval(progressInterval);
          return 90;
        }
        return prev + Math.random() * 15;
      });
    }, 400);

    try {
      const result = await uploadDocuments(files);
      clearInterval(progressInterval);
      setUploadProgress(100);

      if (result.status === 'success') {
        setUploadResult({
          state: 'success',
          message: `✓ ${result.files_processed} file(s) ingested — ${result.total_chunks} chunks added`,
          details: result,
        });
      } else if (result.status === 'partial') {
        setUploadResult({
          state: 'success',
          message: `⚠ ${result.files_processed} processed, ${result.errors.length} failed`,
          details: result,
        });
      } else {
        setUploadResult({
          state: 'error',
          message: result.errors.join(', ') || 'Ingestion failed',
          details: result,
        });
      }

      // Refresh document list
      fetchDocuments();

      // Auto-clear success message after 5s
      setTimeout(() => {
        setUploadResult({ state: 'idle', message: '' });
        setUploadProgress(0);
        setPendingFiles([]);
      }, 5000);
    } catch (err) {
      clearInterval(progressInterval);
      setUploadProgress(0);
      setUploadResult({
        state: 'error',
        message: err instanceof Error ? err.message : 'Upload failed',
      });
    }
  }, [fetchDocuments]);

  // ── File input handlers ────────────────────────────────────────────────

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) handleUpload(files);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleFolderSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) handleUpload(files);
    if (folderInputRef.current) folderInputRef.current.value = '';
  };

  // ── Drag & Drop ───────────────────────────────────────────────────────

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    const items = e.dataTransfer.items;
    const files: File[] = [];

    // Collect files from all entries (including folder contents)
    const readEntry = async (entry: FileSystemEntry): Promise<void> => {
      if (entry.isFile) {
        const file = await new Promise<File>((resolve, reject) => {
          (entry as FileSystemFileEntry).file(resolve, reject);
        });
        files.push(file);
      } else if (entry.isDirectory) {
        const reader = (entry as FileSystemDirectoryEntry).createReader();
        const entries = await new Promise<FileSystemEntry[]>((resolve, reject) => {
          reader.readEntries(resolve, reject);
        });
        for (const child of entries) {
          await readEntry(child);
        }
      }
    };

    if (items) {
      const entries: FileSystemEntry[] = [];
      for (let i = 0; i < items.length; i++) {
        const entry = items[i].webkitGetAsEntry();
        if (entry) entries.push(entry);
      }
      for (const entry of entries) {
        await readEntry(entry);
      }
    }

    if (files.length > 0) {
      handleUpload(files);
    }
  };

  // ── Clear knowledge base ──────────────────────────────────────────────

  const handleClear = async () => {
    if (!confirm('Clear all documents from the knowledge base?')) return;

    try {
      await clearKnowledgeBase();
      setDocuments([]);
      setUploadResult({
        state: 'success',
        message: 'Knowledge base cleared',
      });
      setTimeout(() => setUploadResult({ state: 'idle', message: '' }), 3000);
    } catch (err) {
      setUploadResult({
        state: 'error',
        message: 'Failed to clear knowledge base',
      });
    }
  };

  // ── Total chunks ──────────────────────────────────────────────────────

  const totalChunks = documents.reduce((sum, d) => sum + d.chunks, 0);

  return (
    <div className="mb-4">
      {/* Section Header — clickable toggle */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-3 py-2 rounded-lg hover:bg-surface/50 transition-colors group"
      >
        <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          <Database className="w-4 h-4" />
          Knowledge Base
          {documents.length > 0 && (
            <span className="text-[10px] font-medium normal-case tracking-normal bg-primary/15 text-primary px-1.5 py-0.5 rounded-full">
              {documents.length} doc{documents.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        {isExpanded ? (
          <ChevronUp className="w-4 h-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="w-4 h-4 text-muted-foreground" />
        )}
      </button>

      {/* Expanded content */}
      <div
        className={cn(
          'overflow-hidden transition-all duration-300 ease-in-out',
          isExpanded ? 'max-h-[600px] opacity-100 mt-2' : 'max-h-0 opacity-0'
        )}
      >
        {/* Hidden file inputs */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileSelect}
          className="hidden"
          accept=".pdf,.txt,.md,.csv,.json,.py,.js,.ts,.jsx,.tsx,.html,.css,.xml,.yaml,.yml,.toml,.log,.sql"
        />
        <input
          ref={folderInputRef}
          type="file"
          // @ts-expect-error -- webkitdirectory is non-standard but widely supported
          webkitdirectory=""
          directory=""
          multiple
          onChange={handleFolderSelect}
          className="hidden"
        />

        {/* Drag & Drop Zone */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={cn(
            'relative mx-1 rounded-xl border-2 border-dashed transition-all duration-200 p-4',
            isDragOver
              ? 'border-primary bg-primary/10 scale-[1.02]'
              : 'border-border/60 hover:border-primary/40 bg-surface/30',
            uploadResult.state === 'uploading' && 'pointer-events-none opacity-80'
          )}
        >
          {/* Upload state indicator */}
          {uploadResult.state === 'uploading' ? (
            <div className="flex flex-col items-center gap-3 py-2">
              <div className="relative w-10 h-10">
                <Loader className="w-10 h-10 text-primary animate-spin" />
                <Sparkles className="w-4 h-4 text-primary absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
              </div>
              <p className="text-xs text-foreground/70 font-medium text-center">
                {uploadResult.message}
              </p>

              {/* Progress bar */}
              <div className="w-full h-1.5 bg-surface-dim rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-primary to-primary/60 rounded-full transition-all duration-300 ease-out"
                  style={{ width: `${Math.min(uploadProgress, 100)}%` }}
                />
              </div>

              {/* Pending file names */}
              {pendingFiles.length > 0 && (
                <div className="w-full max-h-16 overflow-y-auto">
                  {pendingFiles.slice(0, 3).map((f, i) => (
                    <p key={i} className="text-[10px] text-muted-foreground truncate">
                      📄 {f.name}
                    </p>
                  ))}
                  {pendingFiles.length > 3 && (
                    <p className="text-[10px] text-muted-foreground">
                      …and {pendingFiles.length - 3} more
                    </p>
                  )}
                </div>
              )}
            </div>
          ) : uploadResult.state === 'success' ? (
            <div className="flex flex-col items-center gap-2 py-2">
              <CheckCircle className="w-8 h-8 text-green-500" />
              <p className="text-xs text-green-600 font-medium text-center">
                {uploadResult.message}
              </p>
            </div>
          ) : uploadResult.state === 'error' ? (
            <div className="flex flex-col items-center gap-2 py-2">
              <AlertCircle className="w-8 h-8 text-red-500" />
              <p className="text-xs text-red-500 font-medium text-center">
                {uploadResult.message}
              </p>
              <button
                onClick={() => setUploadResult({ state: 'idle', message: '' })}
                className="text-[10px] text-muted-foreground hover:text-foreground underline"
              >
                Dismiss
              </button>
            </div>
          ) : (
            /* Default idle state */
            <div className="flex flex-col items-center gap-2 py-1">
              <div className="w-10 h-10 rounded-full bg-primary-container/60 flex items-center justify-center">
                <Upload className="w-5 h-5 text-primary" />
              </div>
              <p className="text-xs text-foreground/70 font-medium">
                Drop files or folders here
              </p>
              <p className="text-[10px] text-muted-foreground">
                PDF, TXT, MD, CSV, JSON, code files…
              </p>
            </div>
          )}
        </div>

        {/* Upload Buttons */}
        <div className="flex gap-2 mx-1 mt-2">
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadResult.state === 'uploading'}
            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-primary-container/50 hover:bg-primary-container text-foreground/80 text-xs font-medium transition-colors disabled:opacity-50"
          >
            <FileText className="w-3.5 h-3.5" />
            Files
          </button>
          <button
            onClick={() => folderInputRef.current?.click()}
            disabled={uploadResult.state === 'uploading'}
            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-primary-container/50 hover:bg-primary-container text-foreground/80 text-xs font-medium transition-colors disabled:opacity-50"
          >
            <FolderOpen className="w-3.5 h-3.5" />
            Folder
          </button>
        </div>

        {/* Stats bar */}
        {documents.length > 0 && (
          <div className="flex items-center justify-between mx-1 mt-3 px-2 py-1.5 rounded-lg bg-surface/60">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                <HardDrive className="w-3 h-3" />
                <span>{documents.length} docs</span>
              </div>
              <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                <Sparkles className="w-3 h-3" />
                <span>{totalChunks} chunks</span>
              </div>
            </div>
            <button
              onClick={handleClear}
              className="p-1 text-muted-foreground hover:text-red-500 transition-colors"
              title="Clear knowledge base"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Document List */}
        {loading ? (
          <div className="flex items-center justify-center py-4">
            <Loader className="w-4 h-4 animate-spin text-muted-foreground" />
          </div>
        ) : documents.length > 0 ? (
          <div className="mx-1 mt-2 max-h-44 overflow-y-auto space-y-1 scrollbar-thin">
            {documents.map((doc, index) => (
              <div
                key={`${doc.name}-${index}`}
                className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-surface/50 transition-colors group"
              >
                <FileIcon className={cn('w-3.5 h-3.5 shrink-0', getFileTypeColor(doc.file_type))} />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-foreground/80 truncate">
                    {doc.name}
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    {doc.chunks} chunks • {doc.file_type}
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-[11px] text-muted-foreground text-center py-3 mx-1">
            No documents ingested yet
          </p>
        )}
      </div>
    </div>
  );
}
