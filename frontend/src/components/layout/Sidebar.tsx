import React, { useState, useEffect } from 'react';
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Sparkles, Plus, History, Trash2, Loader } from "lucide-react";
import { cn } from "@/lib/utils";
import { useChat } from "@/lib/ChatContext";

interface ChatHistoryItem {
  chat_id: string;
  title: string;
  created_at: string;
  message_count: number;
}

export function Sidebar({ isOpen, onClose }: { isOpen: boolean, onClose: () => void }) {
  const { startNewChat, threadId } = useChat();
  const [chatHistory, setChatHistory] = useState<ChatHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchChatHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('http://localhost:8001/api/history/chats');
      if (!response.ok) throw new Error('Failed to fetch chat history');
      const data = await response.json();
      setChatHistory(data);
    } catch (err) {
      console.error('Error fetching chat history:', err);
      setError('Failed to load chat history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchChatHistory();
    }
  }, [isOpen]);

  const handleNewChat = () => {
    startNewChat();
    onClose();
  };

  const handleLoadChat = (chatId: string) => {
    // This would load a specific chat - for now just close
    onClose();
  };

  const handleDeleteChat = async (chatId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const response = await fetch(`http://localhost:8001/api/history/chats/${chatId}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error('Failed to delete chat');
      setChatHistory(chatHistory.filter(c => c.chat_id !== chatId));
    } catch (err) {
      console.error('Error deleting chat:', err);
      setError('Failed to delete chat');
    }
  };
  return (
    <>
      {/* Overlay */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/20 backdrop-blur-sm z-40 transition-opacity"
          onClick={onClose}
        />
      )}
      
      {/* Sidebar Content */}
      <aside className={cn(
        "bg-surface-low border-r border-border fixed left-0 top-0 h-full w-[300px] flex flex-col py-6 px-4 z-50 transition-transform duration-300",
        isOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        {/* Brand Header */}
        <div className="mb-6 flex items-center gap-3 px-3">
          <div className="w-8 h-8 flex items-center justify-center bg-primary-container text-primary rounded-full">
            <Sparkles className="w-5 h-5" />
          </div>
          <h1 className="text-xl font-sans font-medium text-foreground tracking-tight">
            Quantum
          </h1>
        </div>

        {/* Primary Actions */}
        <Button
          onClick={handleNewChat}
          className="mb-6 w-full gap-3 justify-start px-5 h-14 rounded-2xl bg-primary-container text-foreground hover:bg-primary/20 shadow-none hover:shadow-none"
        >
          <Plus className="w-5 h-5 text-primary" />
          <span className="font-medium text-[15px]">New Chat</span>
        </Button>

        {/* Chat History Section */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-3 mb-3">
            <div className="flex items-center gap-2">
              <History className="w-4 h-4" />
              Chat History
            </div>
          </h2>

          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : error ? (
            <div className="px-3 py-2 text-sm text-red-600">{error}</div>
          ) : chatHistory.length === 0 ? (
            <div className="px-3 py-4 text-sm text-muted-foreground text-center">
              No chats yet. Start a new conversation!
            </div>
          ) : (
            <nav className="flex-1 overflow-y-auto space-y-1">
              {chatHistory.map((chat) => {
                const isActive = chat.chat_id === threadId;
                return (
                  <button
                    key={chat.chat_id}
                    onClick={() => handleLoadChat(chat.chat_id)}
                    className={cn(
                      "w-full text-left px-3 py-2 rounded-lg transition-colors group flex items-between justify-between gap-2",
                      isActive
                        ? "bg-primary/20 text-primary"
                        : "text-foreground/70 hover:text-foreground hover:bg-surface/50"
                    )}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {chat.title || `Chat ${chat.chat_id.slice(0, 8)}`}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {chat.message_count} messages
                      </p>
                    </div>
                    <button
                      onClick={(e) => handleDeleteChat(chat.chat_id, e)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:text-red-600"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </button>
                );
              })}
            </nav>
          )}
        </div>
      </aside>
    </>
  );
}
