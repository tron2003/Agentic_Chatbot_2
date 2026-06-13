import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import {
  type ChatMessage,
  type ReasoningStep,
  sendMessage as apiSendMessage,
  streamMessage,
  saveChat as apiSaveChat,
  getChatById,
} from './api';

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

interface ChatContextType {
  messages: ChatMessage[];
  threadId: string;
  isLoading: boolean;
  error: string | null;
  reasoningSteps: ReasoningStep[];
  useStreaming: boolean;
  addMessage: (content: string, role: 'user' | 'assistant') => void;
  sendMessage: (content: string, displayContent?: string) => Promise<void>;
  clearChat: () => void;
  startNewChat: () => void;
  loadChat: (chatId: string) => Promise<void>;
  setError: (error: string | null) => void;
  setUseStreaming: (use: boolean) => void;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [threadId, setThreadId] = useState(() => localStorage.getItem('threadId') || generateId());
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reasoningSteps, setReasoningSteps] = useState<ReasoningStep[]>([]);
  const [useStreaming, setUseStreaming] = useState(
    () => localStorage.getItem('useStreaming') !== 'false'
  );
  const lastSavedLengthRef = useRef(0);

  useEffect(() => {
    localStorage.setItem('threadId', threadId);
  }, [threadId]);

  useEffect(() => {
    localStorage.setItem('useStreaming', String(useStreaming));
  }, [useStreaming]);

  const addMessage = useCallback((content: string, role: 'user' | 'assistant') => {
    const message: ChatMessage = {
      id: generateId(),
      content,
      role,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, message]);
  }, []);

  // Auto-save chat to backend after each assistant response
  useEffect(() => {
    if (
      messages.length >= 2 &&
      !isLoading &&
      messages.length > lastSavedLengthRef.current
    ) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.role === 'assistant') {
        lastSavedLengthRef.current = messages.length;
        const title = messages[0]?.content?.slice(0, 50) || 'New Chat';
        apiSaveChat({
          chat_id: threadId,
          title,
          messages: messages.map(m => ({
            role: m.role,
            content: m.content,
            timestamp: m.timestamp instanceof Date ? m.timestamp.toISOString() : String(m.timestamp),
          })),
        }).catch(err => console.error('Auto-save failed:', err));
      }
    }
  }, [messages, isLoading, threadId]);

  const sendMessage = useCallback(
    async (content: string, displayContent?: string) => {
      if (!content.trim()) return;

      // Show the display version in the UI (without file content blobs)
      addMessage(displayContent || content, 'user');
      setIsLoading(true);
      setError(null);
      setReasoningSteps([]);

      try {
        if (useStreaming) {
          // Use streaming endpoint for agent reasoning visibility
          const steps: ReasoningStep[] = [];
          let finalResponse = '';

          const streamGen = streamMessage({
            message: content,
            thread_id: threadId,
          });

          for await (const event of streamGen) {
            if (event.type === 'reasoning_step') {
              const step = event.data as ReasoningStep;
              steps.push(step);
              setReasoningSteps([...steps]);
            } else if (event.type === 'response') {
              finalResponse = event.data.response;
            } else if (event.type === 'error') {
              setError(event.data.detail);
            } else if (event.type === 'complete') {
              if (finalResponse) {
                addMessage(finalResponse, 'assistant');
              }
            }
          }
        } else {
          // Use traditional non-streaming endpoint
          const response = await apiSendMessage({
            message: content,
            thread_id: threadId,
          });
          addMessage(response, 'assistant');
        }
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'An error occurred';
        setError(errorMessage);
        console.error('Chat error:', err);
      } finally {
        setIsLoading(false);
      }
    },
    [addMessage, threadId, useStreaming]
  );

  const clearChat = useCallback(() => {
    setMessages([]);
    setError(null);
    lastSavedLengthRef.current = 0;
  }, []);

  const startNewChat = useCallback(() => {
    const newThreadId = generateId();
    setThreadId(newThreadId);
    localStorage.setItem('threadId', newThreadId);
    clearChat();
  }, [clearChat]);

  const loadChat = useCallback(async (chatId: string) => {
    try {
      const chatData = await getChatById(chatId);
      setThreadId(chatData.chat_id);
      localStorage.setItem('threadId', chatData.chat_id);
      const loadedMessages: ChatMessage[] = chatData.messages.map((m: any) => ({
        id: generateId(),
        content: m.content,
        role: m.role as 'user' | 'assistant',
        timestamp: new Date(m.timestamp),
      }));
      setMessages(loadedMessages);
      lastSavedLengthRef.current = loadedMessages.length; // Don't re-save loaded chats
      setError(null);
    } catch (err) {
      console.error('Failed to load chat:', err);
      setError('Failed to load chat history');
    }
  }, []);

  return (
    <ChatContext.Provider
      value={{
        messages,
        threadId,
        isLoading,
        error,
        reasoningSteps,
        useStreaming,
        addMessage,
        sendMessage,
        clearChat,
        startNewChat,
        loadChat,
        setError,
        setUseStreaming,
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
