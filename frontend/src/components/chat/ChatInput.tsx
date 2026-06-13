import React, { useRef, useState } from 'react';
import { Paperclip, Camera, ChevronDown, Send, X, File, FolderOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { useChat } from '@/lib/ChatContext';
import { uploadDocuments } from '@/lib/api';

// ---------------------------------------------------------------------------
// File-reading helpers
// ---------------------------------------------------------------------------

const TEXT_EXTENSIONS = [
  '.txt', '.md', '.json', '.csv', '.py', '.js', '.ts', '.jsx', '.tsx',
  '.html', '.css', '.xml', '.yaml', '.yml', '.toml', '.log', '.sql',
  '.sh', '.bat', '.cfg', '.ini', '.env', '.gitignore', '.editorconfig',
];

/** True when the filename or MIME type indicates a text-based file. */
function isTextFile(file: File): boolean {
  return (
    TEXT_EXTENSIONS.some(ext => file.name.toLowerCase().endsWith(ext)) ||
    file.type.startsWith('text/')
  );
}

/** Heuristic: returns true when the string is likely readable text, not binary garble. */
function isReadableContent(text: string): boolean {
  if (!text || text.length < 10) return false;
  const sample = text.slice(0, 500);
  let nonPrintable = 0;
  for (let i = 0; i < sample.length; i++) {
    const code = sample.charCodeAt(i);
    if (code < 32 && code !== 9 && code !== 10 && code !== 13) nonPrintable++;
  }
  return nonPrintable / sample.length < 0.1;
}

/** True for PDF files. */
function isPdfFile(file: File): boolean {
  return file.name.toLowerCase().endsWith('.pdf') || file.type === 'application/pdf';
}

/**
 * Extract human-readable text from a PDF using pdfjs-dist.
 * The worker is loaded from CDN to avoid Vite bundling issues.
 */
async function extractPdfText(file: File): Promise<string> {
  try {
    const pdfjsLib = await import('pdfjs-dist');

    // Use CDN worker — version must match the installed package exactly
    pdfjsLib.GlobalWorkerOptions.workerSrc =
      `https://cdn.jsdelivr.net/npm/pdfjs-dist@${pdfjsLib.version}/build/pdf.worker.min.mjs`;

    const arrayBuffer = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: new Uint8Array(arrayBuffer) }).promise;

    const pages: string[] = [];
    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      const textContent = await page.getTextContent();
      const pageText = textContent.items
        .filter((item: any) => 'str' in item)
        .map((item: any) => item.str)
        .join(' ');
      if (pageText.trim()) {
        pages.push(`[Page ${i}]\n${pageText}`);
      }
    }

    const fullText = pages.join('\n\n');
    return fullText || '[PDF contained no extractable text — it may be a scanned/image-only document]';
  } catch (err) {
    console.error('PDF text extraction failed:', err);
    return `[PDF text extraction failed: ${err instanceof Error ? err.message : String(err)}]`;
  }
}

/**
 * Read a file's content:
 *  - PDFs  → extract text via pdfjs-dist
 *  - Known text types → FileReader.readAsText
 *  - Binary fallback → short metadata string
 */
async function readFileContent(file: File): Promise<string> {
  if (isPdfFile(file)) {
    return extractPdfText(file);
  }

  return new Promise(resolve => {
    const reader = new FileReader();
    reader.onload = () => {
      const text = reader.result as string;
      if (isTextFile(file) || isReadableContent(text)) {
        resolve(text);
      } else {
        resolve(
          `[Binary content – ${file.name}, ${(file.size / 1024).toFixed(1)} KB, type: ${file.type || 'unknown'}]`
        );
      }
    };
    reader.onerror = () => resolve(`[Failed to read ${file.name}]`);
    reader.readAsText(file);
  });
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ChatInput({ inFlow }: { inFlow?: boolean }) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const { sendMessage, isLoading } = useChat();
  const [message, setMessage] = useState('');
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [isIngesting, setIsIngesting] = useState(false);

  const handleInput = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    setAttachedFiles(prev => [...prev, ...files]);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleFolderSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      // Auto-ingest folder contents into the vector store
      setIsIngesting(true);
      try {
        const result = await uploadDocuments(files);
        console.log('Folder ingested:', result);
        // Also attach the files to the current message for context
        setAttachedFiles(prev => [...prev, ...files]);
      } catch (err) {
        console.error('Folder ingestion failed:', err);
        // Still attach them as regular files
        setAttachedFiles(prev => [...prev, ...files]);
      } finally {
        setIsIngesting(false);
      }
    }
    if (folderInputRef.current) {
      folderInputRef.current.value = '';
    }
  };

  const removeFile = (index: number) => {
    setAttachedFiles(prev => prev.filter((_, i) => i !== index));
  };

  // -----------------------------------------------------------------------
  // Submit – read file contents, build two versions of the message:
  //   • apiMessage     → sent to backend (includes full file text)
  //   • displayMessage → shown in the chat UI (compact attachment chips)
  // -----------------------------------------------------------------------
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if ((!message.trim() && attachedFiles.length === 0) || isLoading) return;

    let apiMessage = message;
    let displayMessage = message;

    if (attachedFiles.length > 0) {
      const fileContents: string[] = [];
      const fileNames: string[] = [];

      for (const file of attachedFiles) {
        fileNames.push(file.name);
        try {
          const content = await readFileContent(file);
          fileContents.push(
            `\n--- Content of ${file.name} ---\n${content}\n--- End of ${file.name} ---`
          );
        } catch {
          fileContents.push(`\n[Unable to read ${file.name}]`);
        }
      }

      // Full extracted content goes to the API so the LLM can analyse it
      apiMessage = `${message}\n\nHere are the contents of the attached materials for analysis:\n${fileContents.join('\n')}`;
      // Clean display keeps the UI readable
      displayMessage = `${message}\n📎 ${fileNames.join(', ')}`;
    }

    // sendMessage(apiContent, displayContent) — the context handles both
    await sendMessage(apiMessage, displayMessage);
    setMessage('');
    setAttachedFiles([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && e.shiftKey) {
      return; // Allow shift+enter for new line
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as any);
    }
  };

  return (
    <form onSubmit={handleSubmit} className={cn(
      "w-full flex flex-col gap-3",
      inFlow ? "relative" : "absolute bottom-8 left-1/2 -translate-x-1/2 max-w-3xl px-4 w-full z-20"
    )}>
      {/* Attached Files Display */}
      {attachedFiles.length > 0 && (
        <div className="bg-surface-low border border-border/50 rounded-lg p-3 space-y-2">
          {attachedFiles.map((file, index) => (
            <div key={index} className="flex items-center justify-between gap-2 text-sm">
              <div className="flex items-center gap-2 text-foreground/80">
                <File className="w-4 h-4" />
                <span className="truncate">{file.name}</span>
                <span className="text-muted-foreground">({(file.size / 1024).toFixed(2)}KB)</span>
              </div>
              <button
                type="button"
                onClick={() => removeFile(index)}
                className="p-1 hover:bg-surface rounded transition-colors"
              >
                <X className="w-4 h-4 text-muted-foreground hover:text-foreground" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="bg-surface border border-border/80 shadow-[0_2px_12px_rgba(0,0,0,0.03)] rounded-[24px] focus-within:shadow-[0_8px_30px_rgba(0,0,0,0.06)] focus-within:border-border transition-all overflow-hidden flex flex-col">
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => {
            setMessage(e.target.value);
            handleInput();
          }}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
          className="w-full bg-transparent border-none outline-none focus:ring-0 text-foreground font-sans text-[15px] resize-none px-5 py-4 min-h-[80px] placeholder:text-muted-foreground/60 disabled:opacity-50"
          placeholder="How can Quantum Assistant help you today?"
          rows={2}
        />

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileSelect}
          className="hidden"
          accept=".txt,.pdf,.doc,.docx,.md,.json,.csv,.xlsx,.py,.js,.ts,.jsx,.tsx"
        />
        {/* Hidden folder input */}
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
        
        {/* Input Footer */}
        <div className="flex items-center justify-between px-3 pb-3 mt-auto">
          {/* Model Selector */}
          <button type="button" className="flex items-center gap-1.5 px-3 py-1.5 rounded-full hover:bg-surface-low text-[12px] font-medium text-foreground/70 transition-colors">
            Quantum 3.5 Smart
            <span className="text-primary flex items-center gap-1 ml-1 opacity-90">
              Formal <ChevronDown className="w-3 h-3" />
            </span>
          </button>

          {/* Action Buttons */}
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => folderInputRef.current?.click()}
              disabled={isIngesting}
              title="Upload folder for RAG ingestion"
              className="p-2 text-muted-foreground hover:text-foreground transition-colors hover:bg-surface-low rounded-full disabled:opacity-50"
            >
              <FolderOpen className="w-[18px] h-[18px]" />
            </button>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              title="Attach files (images, documents, code, etc.)"
              className="p-2 text-muted-foreground hover:text-foreground transition-colors hover:bg-surface-low rounded-full"
            >
              <Paperclip className="w-[18px] h-[18px]" />
            </button>
            <button
              type="submit"
              disabled={(!message.trim() && attachedFiles.length === 0) || isLoading || isIngesting}
              className="p-2 text-muted-foreground hover:text-foreground transition-colors hover:bg-surface-low rounded-full disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Send className="w-[18px] h-[18px]" />
            </button>
          </div>
        </div>
      </div>

      {/* Disclaimers & Shortcuts */}
      <div className="flex items-center justify-between px-2 w-full mt-1">
        <p className="text-[11px] text-muted-foreground/80 font-sans">
          Quantum Assistant can make mistakes. Please double-check responses.
        </p>
        <div className="text-[11px] text-muted-foreground/80 items-center gap-1.5 hidden md:flex">
          Use
          <span className="px-1.5 py-0.5 rounded-[4px] bg-surface-low border border-border/40 text-[10px] shadow-sm tracking-wide">
            shift
          </span>
          +
          <span className="px-1.5 py-0.5 rounded-[4px] bg-surface-low border border-border/40 text-[10px] shadow-sm tracking-wide">
            return
          </span>
          for new line
        </div>
      </div>
    </form>
  );
}
