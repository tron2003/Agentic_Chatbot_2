import { useState } from 'react';
import { Sparkles, RefreshCw, Menu } from 'lucide-react';
import { Avatar, AvatarFallback, AvatarImage } from './components/ui/avatar';
import { ChatInput } from './components/chat/ChatInput';
import { ChatMessages } from './components/chat/ChatMessages';
import { Sidebar } from './components/layout/Sidebar';
import { AiModel } from './components/ui/model';
import { BackgroundShader } from './components/ui/shader';
import { ChatProvider, useChat } from './lib/ChatContext';

function AppContent() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const { messages } = useChat();

  return (
    <div className="flex h-screen w-full bg-surface text-foreground font-sans overflow-hidden">
      <Sidebar isOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} />

      <div className="flex flex-col flex-1 relative overflow-hidden bg-transparent">
        {/* Animated Realistic Background */}
        <BackgroundShader />

        {/* Top Bar Navigation */}
        <header className="absolute top-0 left-0 w-full flex justify-between items-center p-5 z-20 mix-blend-multiply">
          <div className="flex items-center gap-4">
            <button 
              className="p-2 -ml-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-full transition-colors"
              onClick={() => setIsSidebarOpen(true)}
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-primary-container text-primary flex items-center justify-center">
                <Sparkles className="w-4 h-4" />
              </div>
              <span className="font-medium text-[15px] tracking-tight text-foreground/90">Quantum Assistant</span>
            </div>
          </div>
          <Avatar className="w-9 h-9 border border-border/80 cursor-pointer hover:opacity-90 transition-opacity">
            <AvatarFallback className="bg-surface-dim font-medium text-[13px] text-foreground">AR</AvatarFallback>
          </Avatar>
        </header>

        {/* Main Canvas Area */}
        <main className="flex-1 flex justify-center items-start md:items-center overflow-y-auto px-6 w-full h-full relative z-10 pt-24 pb-12 scrollbar-none">
          <div className="flex flex-col items-center max-w-[700px] w-full">
            {messages.length === 0 ? (
              // Welcome Screen
              <div className="flex flex-col items-center w-full mt-[-4vh]">
                {/* 3D AI Model */}
                <AiModel />

                {/* Greeting Typography */}
                <h1 className="text-center text-[34px] md:text-[44px] font-medium tracking-tight mb-3 leading-tight text-foreground/95">
                  Good evening, Alex<br />
                  Can I help you with anything?
                </h1>
                <p className="text-center text-[13px] md:text-sm text-foreground/60 mb-10">
                  Choose a prompt below or write your own to start<br className="hidden md:block" /> chatting with Quantum Assistant
                </p>

                {/* Prompt Suggestion Grid */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 w-full mb-3">
                  <PromptCard text="Get fresh perspectives on tricky problems" />
                  <PromptCard text="Brainstorm creative ideas" />
                  <PromptCard text="Rewrite message for maximum impact" />
                  <PromptCard text="Summarize key points" />
                </div>

                {/* Refresh Action */}
                <div className="w-full flex justify-start mb-8 px-1">
                  <button className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted-foreground hover:text-foreground transition-colors font-medium">
                    <RefreshCw className="w-3.5 h-3.5" />
                    Refresh prompts
                  </button>
                </div>

                {/* Chat Input Section */}
                <ChatInput inFlow />
              </div>
            ) : (
              // Chat View
              <div className="flex flex-col items-center w-full">
                <ChatMessages />
                <ChatInput inFlow />
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

function PromptCard({ text }: { text: string }) {
  return (
    <button className="bg-surface-low/80 hover:bg-surface-dim/40 border border-border/30 rounded-xl p-3 md:p-4 text-left transition-colors duration-200 shadow-sm">
      <span className="text-[12px] text-foreground/80 leading-snug font-medium block">
        {text}
      </span>
    </button>
  );
}

export default function App() {
  return (
    <ChatProvider>
      <AppContent />
    </ChatProvider>
  );
}
