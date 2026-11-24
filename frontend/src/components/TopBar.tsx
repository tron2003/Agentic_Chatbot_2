import { Download, Library, PanelLeft } from 'lucide-react';
import { useChat } from '@/lib/chat-store';

export function TopBar({ sidebarOpen, onToggleSidebar, onOpenLibrary }: { sidebarOpen: boolean; onToggleSidebar: () => void; onOpenLibrary: () => void }) {
  const { activeId, conversations, exportConversation, documents } = useChat();
  const title = conversations.find((c) => c.id === activeId)?.title;

  return (
    <header className="pointer-events-none absolute inset-x-0 top-0 z-20">
      <div className="pointer-events-auto flex items-center gap-2 px-3 py-3 sm:px-4">
        {!sidebarOpen && (
          <button
            type="button"
            onClick={onToggleSidebar}
            className="glass rounded-xl border border-line p-2 text-muted hover:text-ink"
            aria-label="Open sidebar"
          >
            <PanelLeft className="size-[18px]" />
          </button>
        )}
        {title ? (
          <h1 className="glass min-w-0 truncate rounded-xl border border-line px-3 py-1.5 text-[14px] font-semibold text-ink">{title}</h1>
        ) : null}
        <div className="ml-auto flex items-center gap-2">
          {activeId && (
            <button
              type="button"
              onClick={() => void exportConversation(activeId)}
              className="glass inline-flex items-center gap-1.5 rounded-xl border border-line px-2.5 py-2 text-[13px] text-muted hover:text-ink"
              title="Download this conversation as Markdown"
            >
              <Download className="size-4" />
              <span className="hidden sm:inline">Export</span>
            </button>
          )}
          <button
            type="button"
            onClick={onOpenLibrary}
            className={`glass ${sidebarOpen ? 'lg:hidden' : ''} inline-flex items-center gap-1.5 rounded-xl border border-line px-2.5 py-2 text-[13px] text-muted hover:text-ink`}
          >
            <Library className="size-4 text-route-docs" />
            <span className="hidden sm:inline">Documents</span>
            {documents.length ? <span className="text-faint">{documents.length}</span> : null}
          </button>
        </div>
      </div>
    </header>
  );
}
