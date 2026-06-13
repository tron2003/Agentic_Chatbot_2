import React, { useRef, useState } from 'react';
import { Paperclip, Camera, ChevronDown, Send, X, File } from "lucide-react";
import { cn } from "@/lib/utils";
import { useChat } from '@/lib/ChatContext';

export function ChatInput({ inFlow }: { inFlow?: boolean }) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { sendMessage, isLoading } = useChat();
  const [message, setMessage] = useState('');
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);

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

  const removeFile = (index: number) => {
    setAttachedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if ((!message.trim() && attachedFiles.length === 0) || isLoading) return;

    let finalMessage = message;

    // Append file information to message if files are attached
    if (attachedFiles.length > 0) {
      const fileInfo = attachedFiles.map(f => `📎 ${f.name} (${(f.size / 1024).toFixed(2)}KB)`).join('\n');
      finalMessage = `${message}\n\n${fileInfo}`;
    }

    await sendMessage(finalMessage);
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
              onClick={() => fileInputRef.current?.click()}
              title="Attach files (images, documents, code, etc.)"
              className="p-2 text-muted-foreground hover:text-foreground transition-colors hover:bg-surface-low rounded-full"
            >
              <Paperclip className="w-[18px] h-[18px]" />
            </button>
            <button
              type="submit"
              disabled={!message.trim() || isLoading}
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
