import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { ChatMessage } from './api';

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

interface ChatContextType {
  messages: ChatMessage[];
  threadId: string;
  isLoading: boolean;
  error: string | null;
  addMessage: (content: string, role: 'user' | 'assistant') => void;
  sendMessage: (content: string) => Promise<void>;
  clearChat: () => void;
  startNewChat: () => void;
  setError: (error: string | null) => void;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [threadId, setThreadId] = useState(() => localStorage.getItem('threadId') || generateId());
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    localStorage.setItem('threadId', threadId);
  }, [threadId]);

  const addMessage = useCallback((content: string, role: 'user' | 'assistant') => {
    const message: ChatMessage = {
      id: generateId(),
      content,
      role,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, message]);
  }, []);

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim()) return;

    addMessage(content, 'user');
    setIsLoading(true);
    setError(null);

    try {
      const { sendMessage: apiSendMessage } = await import('./api');
      const response = await apiSendMessage({
        message: content,
        thread_id: threadId,
      });
      addMessage(response, 'assistant');
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An error occurred';
      setError(errorMessage);
      console.error('Chat error:', err);
    } finally {
      setIsLoading(false);
    }
  }, [addMessage, threadId]);

  const clearChat = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  const startNewChat = useCallback(() => {
    const newThreadId = generateId();
    setThreadId(newThreadId);
    localStorage.setItem('threadId', newThreadId);
    clearChat();
  }, []);

  return (
    <ChatContext.Provider
      value={{
        messages,
        threadId,
        isLoading,
        error,
        addMessage,
        sendMessage,
        clearChat,
        startNewChat,
        setError,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  const context = useContext(ChatContext);
  if (context === undefined) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
}
