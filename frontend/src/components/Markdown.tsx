import { memo, useState, type ReactNode } from 'react';
import ReactMarkdown, { type Components, type Options } from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';
import { Check, Copy } from 'lucide-react';
import { rehypeCaret, splitBlocks } from '@/lib/markdown-stream';

function textOf(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textOf).join('');
  if (node && typeof node === 'object' && 'props' in node) {
    return textOf((node as { props: { children?: ReactNode } }).props.children);
  }
  return '';
}

function CodeBlock({ children, language }: { children: ReactNode; language?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(textOf(children).replace(/\n$/, ''));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard blocked */
    }
  };
  return (
    <div className="group/code relative overflow-hidden rounded-xl border border-line bg-sunk">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-1.5 text-[12px] text-faint">
        <span className="font-mono">{language || 'text'}</span>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-muted hover:bg-raised hover:text-ink"
          aria-label={copied ? 'Copied' : 'Copy code'}
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="scroll-quiet overflow-x-auto px-4 py-3 font-mono text-[13px] leading-[1.6]">{children}</pre>
    </div>
  );
}

const components: Components = {
  pre({ children }) {
    const child = Array.isArray(children) ? children[0] : children;
    const className: string = (child as { props?: { className?: string } })?.props?.className ?? '';
    const language = /language-([\w-]+)/.exec(className)?.[1];
    return <CodeBlock language={language}>{children}</CodeBlock>;
  },
  a({ href, children }) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  },
  table({ children }) {
    return <table className="scroll-quiet">{children}</table>;
  },
};

// Plugin lists are module constants so react-markdown sees the same arrays every render.
const REMARK: Options['remarkPlugins'] = [remarkGfm];
const HIGHLIGHT: Options['rehypePlugins'] = [[rehypeHighlight, { detect: true, ignoreMissing: true }]];
const CARET: Options['rehypePlugins'] = [rehypeCaret];
const NONE: Options['rehypePlugins'] = [];

/**
 * One finished chunk of a streaming answer. Memoised on its text, so once a
 * paragraph or list is complete it is never parsed or rendered again while the
 * rest of the answer is still being typed.
 */
const Block = memo(function Block({ text, caret }: { text: string; caret: boolean }) {
  return (
    <ReactMarkdown remarkPlugins={REMARK} rehypePlugins={caret ? CARET : NONE} components={components} skipHtml>
      {text}
    </ReactMarkdown>
  );
});

export const Markdown = memo(function Markdown({ text, streaming }: { text: string; streaming?: boolean }) {
  if (!streaming) {
    return (
      <div className="prose-answer">
        <ReactMarkdown remarkPlugins={REMARK} rehypePlugins={HIGHLIGHT} components={components} skipHtml>
          {text}
        </ReactMarkdown>
      </div>
    );
  }
  // While streaming, only the last block changes; react-markdown renders no
  // wrapper element, so the blocks are still direct children of .prose-answer.
  const blocks = splitBlocks(text);
  return (
    <div className="prose-answer">
      {blocks.map((block, i) => (
        <Block key={i} text={block} caret={i === blocks.length - 1} />
      ))}
    </div>
  );
});
