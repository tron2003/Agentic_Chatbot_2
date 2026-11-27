import { describe, expect, it } from 'vitest';
import { normalizeMath, rehypeCaret, splitBlocks } from './markdown-stream';

describe('splitBlocks', () => {
  it('splits paragraphs and headings at blank lines', () => {
    expect(splitBlocks('## Title\n\nFirst para.\n\nSecond para.')).toEqual(['## Title\n', 'First para.\n', 'Second para.']);
  });

  it('keeps a list together, even a loose one with blank lines between items', () => {
    const md = 'Intro:\n\n- one\n\n- two\n  continued\n\n1. a\n2. b';
    expect(splitBlocks(md)).toEqual([md]);
  });

  it('starts a new block after a list when an unindented paragraph follows', () => {
    expect(splitBlocks('- a\n- b\n\nAfter.')).toEqual(['- a\n- b\n', 'After.']);
  });

  it('never splits inside a code fence', () => {
    const md = '```py\nx = 1\n\ny = 2\n```\n\nDone.';
    expect(splitBlocks(md)).toEqual(['```py\nx = 1\n\ny = 2\n```\n', 'Done.']);
  });

  it('treats an unclosed fence (still streaming) as one block', () => {
    const md = 'Code:\n\n```js\nconst a = 1;\n\nconst b';
    expect(splitBlocks(md)).toEqual(['Code:\n', '```js\nconst a = 1;\n\nconst b']);
  });

  it('keeps indented continuation and definitions with the previous block', () => {
    expect(splitBlocks('Text [x].\n\n[x]: https://example.com')).toEqual(['Text [x].\n\n[x]: https://example.com']);
    expect(splitBlocks('- item\n\n    indented code')).toEqual(['- item\n\n    indented code']);
  });

  it('round-trips the text', () => {
    const md = '# A\n\nB\n\n- c\n- d\n\n```\ne\n```\n\nf';
    expect(splitBlocks(md).join('\n')).toBe(md);
  });
});

type Node = { type: string; tagName?: string; value?: string; properties?: Record<string, unknown>; children?: Node[] };
const el = (tagName: string, children: Node[] = []): Node => ({ type: 'element', tagName, properties: {}, children });
const text = (value: string): Node => ({ type: 'text', value });
const isCaret = (n?: Node) => n?.tagName === 'span' && (n.properties?.className as string[])?.includes('stream-caret');

describe('rehypeCaret', () => {
  it('puts the caret inside the last list item, not after the list', () => {
    const li2 = el('li', [el('strong', [text('Structural oddities.')]), text(' If P = NP, then N')]);
    const tree: Node = { type: 'root', children: [el('ul', [text('\n'), el('li', [text('one')]), text('\n'), li2, text('\n')]), text('\n')] };
    rehypeCaret()(tree);
    expect(isCaret(li2.children!.at(-1))).toBe(true);
    expect(tree.children!.some(isCaret)).toBe(false);
  });

  it('goes into the last paragraph of a loose list item', () => {
    const p = el('p', [text('deep')]);
    const tree: Node = { type: 'root', children: [el('ol', [el('li', [p])])] };
    rehypeCaret()(tree);
    expect(isCaret(p.children!.at(-1))).toBe(true);
  });

  it('stops at void elements', () => {
    const li = el('li', [el('input'), text(' ')]);
    const tree: Node = { type: 'root', children: [el('ul', [li])] };
    rehypeCaret()(tree);
    expect(isCaret(li.children!.at(-1))).toBe(true);
  });

  it('keeps the caret on the last line of a code block, before the trailing newline', () => {
    const code = el('code', [text('LLM_PROVIDER=claude\n')]);
    const tree: Node = { type: 'root', children: [el('pre', [code])] };
    rehypeCaret()(tree);
    expect(code.children!.map((n) => (isCaret(n) ? '|' : n.value))).toEqual(['LLM_PROVIDER=claude', '|', '\n']);
  });

  it('handles an empty answer', () => {
    const tree: Node = { type: 'root', children: [] };
    rehypeCaret()(tree);
    expect(isCaret(tree.children![0])).toBe(true);
  });
});

describe('normalizeMath', () => {
  it('turns \\[ \\] into a display block and \\( \\) into inline maths', () => {
    expect(normalizeMath('So \\[ 2450 \\times 0.18 = 441 \\] and \\(x^2\\).')).toBe(
      'So \n\n$$\n2450 \\times 0.18 = 441\n$$\n\n and $$x^2$$.',
    );
  });

  it('leaves code and dollar prices alone', () => {
    const text = 'Costs $5 or $10. `\\[a\\]`\n```\n\\(b\\)\n```';
    expect(normalizeMath(text)).toBe(text);
  });
});
