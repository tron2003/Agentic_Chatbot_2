import React, { useEffect, useRef } from 'react';
import { useChat } from '@/lib/ChatContext';
import { Loader } from 'lucide-react';

export function ChatMessages() {
  const { messages, isLoading, error } = useChat();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  if (messages.length === 0 && !isLoading) {
    return null;
  }

  return (
    <div className="w-full max-w-[700px] flex flex-col gap-4 mb-8">
      {messages.map((message) => (
        <div
          key={message.id}
          className={`flex ${
            message.role === 'user' ? 'justify-end' : 'justify-start'
          }`}
        >
          <div
            className={`max-w-[80%] rounded-lg px-4 py-3 ${
              message.role === 'user'
                ? 'bg-primary text-primary-foreground'
                : 'bg-surface-low border border-border/50'
            }`}
          >
            <p className="text-[15px] leading-relaxed whitespace-pre-wrap">
              {message.content}
            </p>
            <span className={`text-[11px] mt-1 block ${
              message.role === 'user'
                ? 'text-primary-foreground/70'
                : 'text-foreground/50'
            }`}>
              {message.timestamp.toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
          </div>
        </div>
      ))}

      {isLoading && (
        <div className="flex justify-start">
          <div className="bg-surface-low border border-border/50 rounded-lg px-4 py-3 flex items-center gap-2">
            <Loader className="w-4 h-4 animate-spin" />
            <span className="text-[14px] text-muted-foreground">
              Quantum Assistant is thinking...
            </span>
          </div>
        </div>
      )}

      {error && (
        <div className="flex justify-start">
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
            <span className="text-[14px] text-red-600">{error}</span>
          </div>
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>
  );
}
