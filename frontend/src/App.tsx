import { useEffect, useState } from 'react';
import { Backdrop } from '@/components/Backdrop';
import { ChatView } from '@/components/ChatView';
import { LibraryPanel } from '@/components/LibraryPanel';
import { ModelPicker } from '@/components/ModelPicker';
import { ApiKeyDialog, SetupBanner, Toasts } from '@/components/Overlays';
import { Sidebar } from '@/components/Sidebar';
import { TopBar } from '@/components/TopBar';
import { Welcome } from '@/components/Welcome';
import { ParallaxProvider } from '@/hooks/parallax';
import { useTheme } from '@/hooks/useTheme';
import { ChatProvider, useChat } from '@/lib/chat-store';
import { cn } from '@/lib/utils';

function focusComposer() {
  requestAnimationFrame(() => document.getElementById('composer-input')?.focus());
}

function Shell() {
  const { hasMessages, activeId, loadingConversation, newChat, stop, streaming, meta } = useChat();
  const { choice, cycle } = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth >= 1024);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const showWelcome = !activeId && !hasMessages && !loadingConversation;

  useEffect(() => {
    if (meta?.app_name) document.title = meta.app_name;
  }, [meta?.app_name]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement)?.closest('input, textarea, [contenteditable="true"]');
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        newChat();
        focusComposer();
      } else if (e.key === 'Escape' && streaming) {
        stop();
      } else if (e.key === '/' && !typing) {
        e.preventDefault();
        focusComposer();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [newChat, stop, streaming]);

  return (
    <div className="relative h-full overflow-hidden">
      <Backdrop />
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onOpenLibrary={() => setLibraryOpen(true)}
        theme={choice}
        onCycleTheme={cycle}
      />
      <main className={cn('relative z-10 h-full transition-[margin] duration-300 ease-out', sidebarOpen && 'lg:ml-[284px]')}>
        <TopBar sidebarOpen={sidebarOpen} onToggleSidebar={() => setSidebarOpen(true)} onOpenLibrary={() => setLibraryOpen(true)} />
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-center">
          <div className="pointer-events-auto">
            <SetupBanner />
          </div>
        </div>
        {showWelcome ? (
          <div className="scroll-quiet h-full overflow-y-auto">
            <Welcome onOpenLibrary={() => setLibraryOpen(true)} />
          </div>
        ) : (
          <ChatView />
        )}
      </main>
      <LibraryPanel open={libraryOpen} onClose={() => setLibraryOpen(false)} />
      <ModelPicker />
      <Toasts />
      <ApiKeyDialog />
    </div>
  );
}

export default function App() {
  return (
    <ChatProvider>
      <ParallaxProvider>
        <Shell />
      </ParallaxProvider>
    </ChatProvider>
  );
}
