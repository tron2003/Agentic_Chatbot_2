/**
 * Smooth, adjustable "typing" reveal for streamed answers.
 *
 * Models often stream faster than anyone can read, and in bursts. Incoming text
 * is queued here and revealed at a steady pace (characters per second) that the
 * reader picks in the sidebar. Code blocks reveal faster, since nobody reads
 * code letter by letter.
 *
 * Only the display is paced: the answer still arrives (and is saved on the
 * server) as fast as the model produces it, and Stop shows the rest at once.
 */

export type TypingSpeed = 'slow' | 'normal' | 'fast' | 'instant';

export const TYPING_SPEEDS: { id: TypingSpeed; label: string; cps: number }[] = [
  { id: 'slow', label: 'Slow', cps: 25 }, // about reading speed
  { id: 'normal', label: 'Normal', cps: 50 },
  { id: 'fast', label: 'Fast', cps: 110 },
  { id: 'instant', label: 'Instant', cps: Number.POSITIVE_INFINITY }, // as fast as it arrives
];

export const DEFAULT_TYPING_SPEED: TypingSpeed = 'normal';

const STORAGE_KEY = 'junction.typingSpeed';
/** Code blocks reveal this many times faster than prose. */
const CODE_SPEEDUP = 4;
/** Longest gap one frame may account for, so a stalled frame doesn't dump a paragraph. */
const MAX_FRAME_MS = 100;
/** Opening/closing Markdown code fences at the start of a line. */
const FENCE = /(^|\n)[ \t]{0,3}(```|~~~)/g;

function isTypingSpeed(value: unknown): value is TypingSpeed {
  return TYPING_SPEEDS.some((s) => s.id === value);
}

export function charsPerSecond(speed: TypingSpeed): number {
  return (TYPING_SPEEDS.find((s) => s.id === speed) ?? TYPING_SPEEDS[1]).cps;
}

/** The reader's saved choice, else VITE_TYPING_SPEED from the build, else "normal". */
export function readTypingSpeed(): TypingSpeed {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (isTypingSpeed(saved)) return saved;
  } catch {
    /* storage unavailable */
  }
  const fromBuild = import.meta.env.VITE_TYPING_SPEED as string | undefined;
  return isTypingSpeed(fromBuild) ? fromBuild : DEFAULT_TYPING_SPEED;
}

export function saveTypingSpeed(speed: TypingSpeed): void {
  try {
    localStorage.setItem(STORAGE_KEY, speed);
  } catch {
    /* storage unavailable */
  }
}

type Schedule = (callback: (now: number) => void) => number;
type Cancel = (handle: number) => void;

function isHighSurrogate(code: number): boolean {
  return code >= 0xd800 && code <= 0xdbff;
}

/**
 * Queues streamed text and hands it to `emit` a few characters per animation
 * frame, at `cps()` characters per second (read every frame, so changing the
 * speed applies mid-answer).
 */
export class Typewriter {
  private readonly emit: (text: string) => void;
  private readonly cps: () => number;
  private readonly schedule: Schedule;
  private readonly cancel: Cancel;

  private queue = '';
  private revealed = '';
  private inCode = false;
  private budget = 0;
  private last: number | null = null;
  private frame = 0;
  private skipping = false;
  private waiters: (() => void)[] = [];

  constructor(
    emit: (text: string) => void,
    cps: () => number,
    schedule: Schedule = (cb) => requestAnimationFrame(cb),
    cancel: Cancel = (handle) => cancelAnimationFrame(handle),
  ) {
    this.emit = emit;
    this.cps = cps;
    this.schedule = schedule;
    this.cancel = cancel;
  }

  /** Characters received but not shown yet. */
  get pending(): number {
    return this.queue.length;
  }

  push(text: string): void {
    if (!text) return;
    if (this.skipping) {
      this.reveal(text);
      return;
    }
    this.queue += text;
    this.request();
  }

  /** Show everything received so far right away; anything arriving later shows immediately too. */
  finish(): void {
    this.skipping = true;
    this.stopFrame();
    if (this.queue) {
      const rest = this.queue;
      this.queue = '';
      this.reveal(rest);
    }
    this.settle();
  }

  /** Forget the current draft (the server restarted the answer). */
  reset(): void {
    this.stopFrame();
    this.queue = '';
    this.revealed = '';
    this.inCode = false;
    this.settle();
  }

  /** Stop for good without showing the rest (the view moved to another conversation). */
  dispose(): void {
    this.stopFrame();
    this.queue = '';
    this.settle();
  }

  /** Resolves once everything received so far has been shown. */
  drain(): Promise<void> {
    if (!this.queue) return Promise.resolve();
    return new Promise((resolve) => this.waiters.push(resolve));
  }

  /** Advance the reveal to time `now` (ms). Driven by animation frames; public for tests. */
  tick(now: number): void {
    this.frame = 0;
    if (!this.queue) {
      this.settle();
      return;
    }
    const base = this.cps();
    let count: number;
    if (!Number.isFinite(base) || base <= 0) {
      count = this.queue.length;
    } else {
      const elapsed = this.last === null ? 1000 / 60 : Math.min(Math.max(now - this.last, 0), MAX_FRAME_MS);
      this.budget += (base * (this.inCode ? CODE_SPEEDUP : 1) * elapsed) / 1000;
      count = Math.min(Math.floor(this.budget), this.queue.length);
    }
    this.last = now;

    if (count > 0) {
      // Never split an emoji (or any surrogate pair) across frames.
      if (count < this.queue.length && isHighSurrogate(this.queue.charCodeAt(count - 1))) count += 1;
      const chunk = this.queue.slice(0, count);
      this.queue = this.queue.slice(count);
      this.budget = Math.max(0, this.budget - count);
      this.reveal(chunk);
    }

    if (this.queue) this.request();
    else this.settle();
  }

  private reveal(text: string): void {
    this.revealed += text;
    this.inCode = (this.revealed.match(FENCE)?.length ?? 0) % 2 === 1;
    this.emit(text);
  }

  private request(): void {
    if (!this.frame) this.frame = this.schedule((now) => this.tick(now));
  }

  private stopFrame(): void {
    if (this.frame) this.cancel(this.frame);
    this.frame = 0;
  }

  /** Called whenever the queue may be empty: reset pacing and wake anyone waiting on drain(). */
  private settle(): void {
    if (this.queue) return;
    this.last = null;
    this.budget = 0;
    const waiters = this.waiters;
    this.waiters = [];
    waiters.forEach((resolve) => resolve());
  }
}
