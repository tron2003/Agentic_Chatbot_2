import { useRef, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { Composer, type ComposerHandle } from './Composer';
import { RouteMap } from './RouteMap';
import { useChat } from '@/lib/chat-store';
import { ROUTE_LABEL, type Route } from '@/lib/types';
import { cn } from '@/lib/utils';

const DOT: Record<Route, string> = { chat: 'bg-route-chat', rag: 'bg-route-docs', agent: 'bg-route-agent' };

export function Welcome({ onOpenLibrary }: { onOpenLibrary: () => void }) {
  const { meta, documents, send } = useChat();
  const [hover, setHover] = useState<Route | null>(null);
  const composer = useRef<ComposerHandle>(null);
  const reduced = useReducedMotion();

  const hasDocs = documents.length > 0;
  const web = meta?.web_search ?? false;

  const descriptions: Record<Route, string> = {
    chat: 'a direct answer',
    rag: hasDocs ? `${documents.length} ${documents.length === 1 ? 'file' : 'files'}, cited` : 'your files, cited',
    agent: web ? 'web search and tools' : 'tools (web search off)',
  };

  const suggestions: { route: Route; text: string; action?: () => void }[] = [
    { route: 'chat', text: 'Explain the difference between RAG and fine-tuning' },
    hasDocs
      ? { route: 'rag', text: `Summarize the key points of ${documents[0].name}` }
      : { route: 'rag', text: 'Add a document to your library, then ask about it', action: onOpenLibrary },
    web
      ? { route: 'agent', text: "What's new in the latest LangGraph release?" }
      : { route: 'agent', text: 'How many days are left until 1 January 2027?' },
  ];

  const enter = (delay: number) =>
    reduced ? {} : { initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.5, delay, ease: [0.2, 0.7, 0.2, 1] as const } };

  return (
    <div className="mx-auto flex min-h-full w-full max-w-[760px] flex-col justify-center px-4 pb-8 pt-20 sm:px-6">
      <div className="mb-2 -ml-1 sm:mb-4">
        <RouteMap highlight={hover} labels={ROUTE_LABEL} descriptions={descriptions} />
      </div>

      <motion.h1 {...enter(0.15)} className="text-[clamp(2rem,5.4vw,3.35rem)] font-[820] leading-[1.02] tracking-[-0.025em] text-ink text-balance">
        Ask anything. Junction picks the route.
      </motion.h1>
      <motion.p {...enter(0.25)} className="mt-4 max-w-[58ch] text-[16px] leading-relaxed text-muted text-pretty">
        Quick questions get a direct answer. Questions about your files search your library and cite it. Anything current goes to
        research, which uses tools{web ? ' and the web' : ''} before answering.
      </motion.p>

      <motion.ul {...enter(0.35)} className="mt-7 divide-y divide-line border-y border-line" aria-label="Example questions">
        {suggestions.map((s) => (
          <li key={s.route}>
            <button
              type="button"
              onMouseEnter={() => setHover(s.route)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(s.route)}
              onBlur={() => setHover(null)}
              onClick={() => (s.action ? s.action() : void send(s.text))}
              className="group flex w-full items-start gap-3 py-3.5 text-left sm:items-center sm:gap-4"
            >
              <span className={cn('mt-[7px] size-2.5 shrink-0 rounded-full sm:mt-0', DOT[s.route])} />
              <span className="flex min-w-0 flex-1 flex-col sm:flex-row sm:items-center sm:gap-4">
                <span className="shrink-0 text-[13px] font-semibold text-muted sm:w-[5.5rem]">{ROUTE_LABEL[s.route]}</span>
                <span className="min-w-0 flex-1 text-[15px] text-ink group-hover:underline group-hover:decoration-line-strong group-hover:underline-offset-4">
                  {s.text}
                </span>
              </span>
            </button>
          </li>
        ))}
      </motion.ul>

      <motion.div {...enter(0.45)} className="mt-8">
        <Composer ref={composer} autoFocus placeholder="Ask a question, or attach a file" />
      </motion.div>
    </div>
  );
}
