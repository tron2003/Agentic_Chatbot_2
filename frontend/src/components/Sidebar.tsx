'use client'

import React, { useState, useEffect } from 'react'
import { Plus, MessageSquare, Trash2, ChevronDown, Menu, X } from 'lucide-react'
import { generateChatId, formatChatIdForDisplay, formatChatDate } from '@/utils/chatId'

interface ChatHistoryItem {
  id: string
  title: string
  createdAt: Date
  messageCount: number
}

interface SidebarProps {
  currentChatId: string | null
  onNewChat: (chatId: string) => void
  onSelectChat: (chatId: string) => void
  onDeleteChat: (chatId: string) => void
  chatHistory: ChatHistoryItem[]
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentChatId,
  onNewChat,
  onSelectChat,
  onDeleteChat,
  chatHistory,
}) => {
  const [isOpen, setIsOpen] = useState(true)
  const [isLoading, setIsLoading] = useState(false)

  const handleNewChat = async () => {
    setIsLoading(true)
    try {
      const newChatId = generateChatId()
      onNewChat(newChatId)
    } finally {
      setIsLoading(false)
    }
  }

  const handleDeleteChat = (e: React.MouseEvent, chatId: string) => {
    e.stopPropagation()
    if (confirm('Delete this chat? This action cannot be undone.')) {
      onDeleteChat(chatId)
    }
  }

  return (
    <>
      {/* Mobile toggle button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="hidden sm:hidden md:hidden lg:flex fixed bottom-4 left-4 z-50 p-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors"
        title="Toggle sidebar"
      >
        {isOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>

      {/* Sidebar overlay for mobile */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 lg:hidden z-30 transition-opacity"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed left-0 top-0 h-screen w-64 bg-gray-900 text-gray-100 shadow-2xl transition-transform duration-300 ease-in-out z-40 ${
          isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        {/* Header */}
        <div className="flex flex-col h-full">
          <div className="p-4 border-b border-gray-700">
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <MessageSquare className="w-5 h-5 text-blue-400" />
              ChatBot
            </h2>
            <p className="text-xs text-gray-400 mt-1">Chat History</p>
          </div>

          {/* New Chat Button */}
          <button
            onClick={handleNewChat}
            disabled={isLoading}
            className="m-4 w-[calc(100%-2rem)] flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium"
          >
            <Plus className="w-5 h-5" />
            <span>{isLoading ? 'Creating...' : 'New Chat'}</span>
          </button>

          {/* Chat History List */}
          <div className="flex-1 overflow-y-auto p-2 space-y-2">
            {chatHistory.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-400">
                <MessageSquare className="w-8 h-8 mb-2 opacity-50" />
                <p className="text-sm text-center">No chats yet.</p>
                <p className="text-xs text-center mt-2">Start a conversation to create a new chat.</p>
              </div>
            ) : (
              chatHistory.map((chat) => (
                <button
                  key={chat.id}
                  onClick={() => onSelectChat(chat.id)}
                  className={`w-full text-left px-3 py-2 rounded-lg transition-colors group ${
                    currentChatId === chat.id
                      ? 'bg-blue-600 text-white'
                      : 'hover:bg-gray-800 text-gray-200'
                  }`}
                  title={chat.title}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{chat.title}</p>
                      <div className="flex gap-2 text-xs text-gray-400 mt-1">
                        <span>{formatChatIdForDisplay(chat.id)}</span>
                        <span>•</span>
                        <span>{formatChatDate(chat.createdAt)}</span>
                      </div>
                    </div>
                    <button
                      onClick={(e) => handleDeleteChat(e, chat.id)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-red-600 rounded ml-2 flex-shrink-0"
                      title="Delete chat"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </button>
              ))
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-gray-700 p-4 text-xs text-gray-400">
            <p>v1.0.0</p>
            <p className="mt-2">© 2024 Agentic Chatbot</p>
          </div>
        </div>
      </aside>

      {/* Main content spacing */}
      <div className={`transition-all duration-300 ${isOpen ? 'lg:ml-64' : ''}`} />
    </>
  )
}

export default Sidebar
