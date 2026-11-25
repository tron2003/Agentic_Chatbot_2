import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ArrowDown, Loader2 } from 'lucide-react';
import { Composer } from './Composer';
import { Message } from './Message';
import { useScrollParallax } from '@/hooks/parallax';
import { useChat, useMessages } from '@/lib/chat-store';

export function ChatView() {
  const { regenerate, streaming, loadingConversation, activeId } = useChat();
  const messages = useMessages();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);
  const [announce, setAnnounce] = useState('');
  // While the list follows a streaming answer, the background holds still:
  // moving it every frame forced every frosted-glass panel to re-blur.
  useScrollParallax(scrollRef, streaming && pinned);

  // Follow the answer while it streams, unless the reader scrolled up.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el || !pinned) return;
    const bottom = el.scrollHeight - el.clientHeight;
    if (el.scrollTop < bottom - 1) el.scrollTop = bottom;
  }, [messages, pinned]);

  useEffect(() => {
    setPinned(true);
  }, [activeId]);

  const last = messages[messages.length - 1];
  useEffect(() => {
    if (!streaming && last?.role === 'assistant' && last.status === 'done') setAnnounce('Answer ready.');
  }, [streaming, last?.status, last?.role]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    setPinned((p) => (p === atBottom ? p : atBottom));
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="scroll-quiet relative min-h-0 flex-1 overflow-y-auto [mask-image:linear-gradient(to_bottom,transparent_0,transparent_40px,black_96px)]"
      >
        <div className="mx-auto w-full max-w-[760px] px-4 pb-10 pt-24 sm:px-6">
          {loadingConversation && !messages.length ? (
            <div className="flex items-center gap-2 py-16 text-muted">
              <Loader2 className="size-4 animate-spin" /> Opening the conversation
            </div>
          ) : (
            <div className="space-y-9">
              {messages.map((m, i) => (
                <Message key={m.id} message={m} isLast={i === messages.length - 1} onRegenerate={regenerate} busy={streaming} />
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="relative mx-auto w-full max-w-[760px] shrink-0 px-4 pb-4 sm:px-6">
        {!pinned && (
          <button
            type="button"
            onClick={() => {
              setPinned(true);
              scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
            }}
            className="glass absolute -top-12 left-1/2 inline-flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-[13px] text-ink shadow-lift transition hover:border-line-strong active:scale-[0.97]"
          >
            <ArrowDown className="size-3.5" /> Latest
          </button>
        )}
        <div>
          <Composer placeholder="Ask a follow-up" />
          <p className="mt-2 text-center text-[12px] text-faint">Answers can be wrong. Check sources for anything important.</p>
        </div>
      </div>
      <div className="sr-only" aria-live="polite">
        {announce}
      </div>
    </div>
  );
}
