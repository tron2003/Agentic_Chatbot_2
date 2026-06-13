import React from 'react';
import { Sparkles, User } from "lucide-react";
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";

type MessageProps = {
  role: 'ai' | 'user';
  content: React.ReactNode;
  isTyping?: boolean;
};

export function ChatMessage({ role, content, isTyping }: MessageProps) {
  const isAI = role === 'ai';

  return (
    <div className={cn(
      "flex flex-col w-full group mb-6",
      !isAI && "items-end"
    )}>
      <div className={cn(
        "flex items-end gap-3 max-w-[85%]",
        !isAI && "flex-row-reverse"
      )}>
        {isAI ? (
          <div className="w-8 h-8 rounded-full bg-primary-container flex items-center justify-center shrink-0 mb-2">
            <Sparkles className="w-4 h-4 text-primary" />
          </div>
        ) : (
          <Avatar className="w-8 h-8 rounded-full shrink-0 border border-border mb-2">
            <AvatarImage src="https://i.pravatar.cc/150?u=a042581f4e29026024d" className="object-cover" />
            <AvatarFallback className="bg-primary text-primary-foreground">
              <User className="w-4 h-4" />
            </AvatarFallback>
          </Avatar>
        )}

        <div className={cn(
          "px-5 py-4 font-sans text-[15px] leading-relaxed relative rounded-3xl",
          isAI 
            ? "bg-surface-low text-foreground rounded-bl-sm" 
            : "bg-primary text-primary-foreground rounded-br-sm"
        )}>
          {isTyping ? (
            <div className="flex items-center gap-1.5 h-6">
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" style={{ animationDelay: '0.1s' }} />
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" style={{ animationDelay: '0.2s' }} />
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" style={{ animationDelay: '0.3s' }} />
            </div>
          ) : content}
        </div>
      </div>
    </div>
  );
}

export function CodeBlock({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-surface border border-border rounded-xl p-4 font-mono text-[13px] overflow-x-auto my-4 text-foreground shadow-sm">
      {children}
    </div>
  );
}
