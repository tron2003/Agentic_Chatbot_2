'use client'

import { useState, useRef, useEffect } from 'react'
import { Send, Bot, User, Loader2, Settings, Info } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Sidebar from '@/components/Sidebar'
import { generateChatId, getChatDisplayName } from '@/utils/chatId'

interface Message {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

interface ChatState {
  messages: Message[]
  isLoading: boolean
  error: string | null
}

interface ChatHistoryItem {
  id: string
  title: string
  createdAt: Date
  messageCount: number
}

export default function Home() {
  // Chat state
  const [currentChatId, setCurrentChatId] = useState<string | null>(null)
  const [chatHistory, setChatHistory] = useState<ChatHistoryItem[]>([])
  const [chatState, setChatState] = useState<ChatState>({
    messages: [],
    isLoading: false,
    error: null,
  })
  const [inputValue, setInputValue] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Load chat history from localStorage
  useEffect(() => {
    const savedHistory = localStorage.getItem('chatHistory')
    if (savedHistory) {
      try {
        const parsed = JSON.parse(savedHistory)
        const withDates = parsed.map((chat: any) => ({
          ...chat,
          createdAt: new Date(chat.createdAt),
        }))
        setChatHistory(withDates)
      } catch (e) {
        console.error('Failed to parse chat history:', e)
      }
    }
  }, [])

  // Save chat history to localStorage
  useEffect(() => {
    localStorage.setItem('chatHistory', JSON.stringify(chatHistory))
  }, [chatHistory])

  // Load chat messages when selecting a chat
  useEffect(() => {
    if (currentChatId) {
      const savedChats = localStorage.getItem(`chat_${currentChatId}`)
      if (savedChats) {
        try {
          const parsed = JSON.parse(savedChats)
          const withDates = parsed.map((msg: any) => ({
            ...msg,
            timestamp: new Date(msg.timestamp),
          }))
          setChatState({
            messages: withDates,
            isLoading: false,
            error: null,
          })
        } catch (e) {
          console.error('Failed to load chat:', e)
          setChatState({ messages: [], isLoading: false, error: null })
        }
      } else {
        setChatState({ messages: [], isLoading: false, error: null })
      }
    }
  }, [currentChatId])

  // Save messages when they change
  useEffect(() => {
    if (currentChatId) {
      localStorage.setItem(`chat_${currentChatId}`, JSON.stringify(chatState.messages))
    }
  }, [chatState.messages, currentChatId])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [chatState.messages])

  const handleNewChat = (chatId: string) => {
    setCurrentChatId(chatId)
    setChatState({ messages: [], isLoading: false, error: null })
    setInputValue('')

    // Add to history
    setChatHistory((prev) => [
      {
        id: chatId,
        title: 'New Chat',
        createdAt: new Date(),
        messageCount: 0,
      },
      ...prev,
    ])
  }

  const handleSelectChat = (chatId: string) => {
    setCurrentChatId(chatId)
  }

  const handleDeleteChat = (chatId: string) => {
    setChatHistory((prev) => prev.filter((chat) => chat.id !== chatId))
    localStorage.removeItem(`chat_${chatId}`)

    if (currentChatId === chatId) {
      if (chatHistory.length > 1) {
        const nextChat = chatHistory.find((c) => c.id !== chatId)
        if (nextChat) {
          setCurrentChatId(nextChat.id)
        }
      } else {
        setCurrentChatId(null)
        setChatState({ messages: [], isLoading: false, error: null })
      }
    }
  }

  const handleSendMessage = async () => {
    if (!inputValue.trim() || chatState.isLoading) return

    // Create new chat if not exists
    if (!currentChatId) {
      const newChatId = generateChatId()
      handleNewChat(newChatId)
    }

    const userMessage: Message = {
      role: 'user',
      content: inputValue,
      timestamp: new Date(),
    }

    setChatState((prev) => ({
      ...prev,
      messages: [...prev.messages, userMessage],
      isLoading: true,
      error: null,
    }))

    setInputValue('')

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: inputValue,
          thread_id: currentChatId || generateChatId(),
        }),
      })

      if (!response.ok) {
        throw new Error('Failed to get response')
      }

      const data = await response.json()
      const assistantMessage: Message = {
        role: 'assistant',
        content: data.response,
        timestamp: new Date(),
      }

      setChatState((prev) => ({
        ...prev,
        messages: [...prev.messages, assistantMessage],
        isLoading: false,
      }))

      // Update chat title based on first message
      if (currentChatId && chatState.messages.length === 0) {
        setChatHistory((prev) =>
          prev.map((chat) =>
            chat.id === currentChatId
              ? { ...chat, title: getChatDisplayName(inputValue) }
              : chat
          )
        )
      }

      // Update message count
      setChatHistory((prev) =>
        prev.map((chat) =>
          chat.id === currentChatId
            ? { ...chat, messageCount: chat.messageCount + 2 }
            : chat
        )
      )
    } catch (error) {
      setChatState((prev) => ({
        ...prev,
        isLoading: false,
        error: error instanceof Error ? error.message : 'An error occurred',
      }))
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  const clearChat = () => {
    setChatState({
      messages: [],
      isLoading: false,
      error: null,
    })
  }

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  const CodeBlock = ({ children, className }: { children: string; className?: string }) => {
    const match = /language-(\w+)/.exec(className || '')
    return match ? (
      <SyntaxHighlighter
        style={vscDarkPlus}
        language={match[1]}
        customStyle={{
          margin: '1rem 0',
          borderRadius: '0.5rem',
          fontSize: '0.875rem',
        }}
      >
        {String(children).trim()}
      </SyntaxHighlighter>
    ) : (
      <code className={className} style={{ background: 'hsl(var(--muted))', padding: '0.2rem 0.4rem', borderRadius: '0.25rem' }}>
        {children}
      </code>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800 flex">
      {/* Sidebar */}
      <Sidebar
        currentChatId={currentChatId}
        onNewChat={handleNewChat}
        onSelectChat={handleSelectChat}
        onDeleteChat={handleDeleteChat}
        chatHistory={chatHistory}
      />

      {/* Main content */}
      <main className="flex-1 lg:ml-64">
        <div className="container mx-auto px-4 py-8 max-w-4xl">
          {/* Header */}
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center space-x-3">
              <div className="p-3 bg-gradient-to-r from-blue-500 to-purple-600 rounded-lg">
                <Bot className="w-8 h-8 text-white" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Agentic Chatbot</h1>
                <p className="text-gray-600 dark:text-gray-300">
                  {currentChatId ? `Chat ID: ${currentChatId.split('_')[1]?.slice(-8)}` : 'Start a new chat'}
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={clearChat}
                className="p-2 text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white transition-colors"
                title="Clear chat"
              >
                <Settings className="w-5 h-5" />
              </button>
              <button className="p-2 text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white transition-colors" title="About">
                <Info className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Chat Container */}
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl overflow-hidden">
            {/* Messages Area */}
            <div className="h-[70vh] overflow-y-auto p-6 space-y-4 chat-scroll">
              {chatState.messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-gray-500 dark:text-gray-400">
                  <Bot className="w-16 h-16 mb-4 opacity-50" />
                  <h3 className="text-xl font-semibold mb-2">Welcome to Agentic Chatbot</h3>
                  <p className="text-center max-w-md">Start a conversation with AI. The bot has access to memory, tools, and can help with various tasks.</p>
                </div>
              ) : (
                chatState.messages.map((message, index) => (
                  <div
                    key={index}
                    className={`flex gap-4 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    {message.role === 'assistant' && (
                      <div className="flex-shrink-0">
                        <div className="w-10 h-10 bg-gradient-to-r from-blue-500 to-purple-600 rounded-full flex items-center justify-center">
                          <Bot className="w-5 h-5 text-white" />
                        </div>
                      </div>
                    )}
                    <div className={`max-w-[80%] ${message.role === 'user' ? 'order-1' : ''}`}>
                      <div
                        className={`rounded-2xl px-4 py-3 ${
                          message.role === 'user'
                            ? 'bg-blue-500 text-white'
                            : 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100'
                        }`}
                      >
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            code: CodeBlock,
                            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                            ul: ({ children }) => <ul className="list-disc list-inside mb-2 last:mb-0">{children}</ul>,
                            ol: ({ children }) => <ol className="list-decimal list-inside mb-2 last:mb-0">{children}</ol>,
                            blockquote: ({ children }) => (
                              <blockquote className="border-l-4 border-blue-500 pl-4 mb-2 dark:border-blue-400">
                                {children}
                              </blockquote>
                            ),
                            h1: ({ children }) => <h1 className="text-xl font-bold mb-2">{children}</h1>,
                            h2: ({ children }) => <h2 className="text-lg font-semibold mb-2">{children}</h2>,
                            h3: ({ children }) => <h3 className="text-md font-medium mb-2">{children}</h3>,
                          }}
                        >
                          {message.content}
                        </ReactMarkdown>
                      </div>
                      <div className={`text-xs text-gray-500 mt-1 ${message.role === 'user' ? 'text-right' : ''}`}>
                        {formatTime(message.timestamp)}
                      </div>
                    </div>
                    {message.role === 'user' && (
                      <div className="flex-shrink-0">
                        <div className="w-10 h-10 bg-gray-200 dark:bg-gray-600 rounded-full flex items-center justify-center">
                          <User className="w-5 h-5 text-gray-600 dark:text-gray-300" />
                        </div>
                      </div>
                    )}
                  </div>
                ))
              )}

              {chatState.isLoading && (
                <div className="flex gap-4 justify-start">
                  <div className="flex-shrink-0">
                    <div className="w-10 h-10 bg-gradient-to-r from-blue-500 to-purple-600 rounded-full flex items-center justify-center">
                      <Bot className="w-5 h-5 text-white" />
                    </div>
                  </div>
                  <div className="bg-gray-100 dark:bg-gray-700 rounded-2xl px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin text-gray-500" />
                      <span className="text-gray-600 dark:text-gray-300">Thinking...</span>
                    </div>
                  </div>
                </div>
              )}

              {chatState.error && (
                <div className="bg-red-100 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                  <div className="flex items-center gap-2 text-red-700 dark:text-red-300">
                    <Info className="w-5 h-5" />
                    <span className="font-medium">Error</span>
                  </div>
                  <p className="text-red-600 dark:text-red-200 mt-1">{chatState.error}</p>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
            <div className="border-t border-gray-200 dark:border-gray-700 p-4">
              <div className="flex gap-3">
                <div className="flex-1 relative">
                  <textarea
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyDown={handleKeyPress}
                    placeholder="Type your message..."
                    className="w-full resize-none rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-4 py-3 pr-12 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:focus:ring-blue-400"
                    rows={1}
                    disabled={chatState.isLoading}
                  />
                  <div className="absolute right-2 bottom-2 flex items-center gap-1">
                    <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                    <span className="text-xs text-gray-500">Connected</span>
                  </div>
                </div>
                <button
                  onClick={handleSendMessage}
                  disabled={!inputValue.trim() || chatState.isLoading}
                  className={`p-3 rounded-lg transition-colors ${
                    inputValue.trim() && !chatState.isLoading
                      ? 'bg-blue-500 hover:bg-blue-600 text-white'
                      : 'bg-gray-200 dark:bg-gray-600 text-gray-400 cursor-not-allowed'
                  }`}
                >
                  {chatState.isLoading ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <Send className="w-5 h-5" />
                  )}
                </button>
              </div>
              <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                Press Enter to send, Shift+Enter for new line
              </div>
            </div>
          </div>

          {/* Features */}
          <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-lg">
              <div className="w-12 h-12 bg-blue-100 dark:bg-blue-900/20 rounded-lg flex items-center justify-center mb-4">
                <Bot className="w-6 h-6 text-blue-600 dark:text-blue-400" />
              </div>
              <h3 className="font-semibold text-gray-900 dark:text-white mb-2">AI Memory</h3>
              <p className="text-gray-600 dark:text-gray-300 text-sm">The bot remembers context from previous conversations for better responses.</p>
            </div>
            <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-lg">
              <div className="w-12 h-12 bg-purple-100 dark:bg-purple-900/20 rounded-lg flex items-center justify-center mb-4">
                <Settings className="w-6 h-6 text-purple-600 dark:text-purple-400" />
              </div>
              <h3 className="font-semibold text-gray-900 dark:text-white mb-2">Smart Tools</h3>
              <p className="text-gray-600 dark:text-gray-300 text-sm">Access to web search, PDF processing, and other intelligent tools.</p>
            </div>
            <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-lg">
              <div className="w-12 h-12 bg-green-100 dark:bg-green-900/20 rounded-lg flex items-center justify-center mb-4">
                <Info className="w-6 h-6 text-green-600 dark:text-green-400" />
              </div>
              <h3 className="font-semibold text-gray-900 dark:text-white mb-2">Chat History</h3>
              <p className="text-gray-600 dark:text-gray-300 text-sm">Keep track of all your conversations with persistent chat history.</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
