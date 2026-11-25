/**
 * Helpers for rendering an answer while it is still being typed.
 *
 * splitBlocks() cuts the Markdown into top-level blocks so finished blocks can
 * be memoised and only the last one re-parsed on each frame. rehypeCaret() puts
 * the typing caret inside the last line of text, instead of after the last
 * block element (which dropped it onto its own line below lists and tables).
 */

/** List item marker at the start of a line: "-", "*", "+", "1.", "1)". */
const LIST_ITEM = /^([*+-]|\d{1,9}[.)])(\s|$)/;
/** Link reference or footnote definition: "[x]: url", "[^1]: note". */
const DEFINITION = /^\[\^?[^\]]+\]:/;
/** Code fence opener/closer, up to three spaces of indent. */
const FENCE = /^ {0,3}(`{3,}|~{3,})(.*)$/;

/**
 * Split Markdown at blank lines where a new top-level block certainly starts.
 *
 * It only splits before a line that starts at column 0 and isn't a list item
 * or a definition, and never inside a code fence. At such a point CommonMark
 * has closed every open block, so rendering the pieces one after another gives
 * the same result as rendering the whole text (link references defined later
 * are the one exception; the finished answer is rendered whole, so they
 * resolve once it's complete).
 */
export function splitBlocks(text: string): string[] {
  const lines = text.split('\n');
  const blocks: string[] = [];
  let current: string[] = [];
  let fence: string | null = null;
  let afterBlank = false;

  for (const line of lines) {
    if (fence) {
      current.push(line);
      const m = FENCE.exec(line);
      if (m && m[1][0] === fence[0] && m[1].length >= fence.length && !m[2].trim()) fence = null;
      continue;
    }

    const startsBlock = afterBlank && /^\S/.test(line) && !LIST_ITEM.test(line) && !DEFINITION.test(line);
    if (startsBlock && current.some((l) => l.trim())) {
      blocks.push(current.join('\n'));
      current = [];
    }
    current.push(line);

    const open = FENCE.exec(line);
    if (open) fence = open[1];
    afterBlank = !line.trim();
  }
  blocks.push(current.join('\n'));
  return blocks;
}

/** The parts of a hast node this plugin touches (avoids a direct dependency on @types/hast). */
interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

/** Elements that can't hold the caret. */
const VOID = new Set(['br', 'hr', 'img', 'input', 'wbr']);

/** Rehype plugin: append the typing caret to the deepest last element, i.e. right after the last character. */
export function rehypeCaret() {
  return (tree: HastNode) => {
    let target = tree;
    for (;;) {
      const kids = target.children ?? [];
      let i = kids.length - 1;
      while (i >= 0 && kids[i].type === 'text' && !kids[i].value?.trim()) i--;
      const last = kids[i];
      if (last && last.type === 'element' && !VOID.has(last.tagName ?? '')) {
        target = last;
        continue;
      }
      break;
    }
    const caret: HastNode = { type: 'element', tagName: 'span', properties: { className: ['stream-caret'], ariaHidden: 'true' }, children: [] };
    const kids = [...(target.children ?? [])];
    const last = kids[kids.length - 1];
    // Code text ends with a newline; put the caret before it, not on the empty line below.
    const trailing = last?.type === 'text' ? /\n+$/.exec(last.value ?? '')?.[0] : undefined;
    if (last && trailing && last.value!.trim()) {
      kids[kids.length - 1] = { ...last, value: last.value!.slice(0, -trailing.length) };
      kids.push(caret, { type: 'text', value: trailing });
    } else {
      kids.push(caret);
    }
    target.children = kids;
  };
}
