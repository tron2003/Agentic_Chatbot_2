import { describe, expect, it } from 'vitest';
import { charsPerSecond, Typewriter } from './typing';

/** A Typewriter driven by a fake clock: frames run only when `run(ms)` is called. */
function setup(cps: number) {
  let shown = '';
  let speed = cps;
  let queued: ((now: number) => void) | null = null;
  let now = 0;
  const tw = new Typewriter(
    (text) => {
      shown += text;
    },
    () => speed,
    (cb) => {
      queued = cb;
      return 1;
    },
    () => {
      queued = null;
    },
  );
  /** Advance the clock in 1/60 s frames for `ms` milliseconds. */
  const run = (ms: number) => {
    for (let t = 0; t < ms; t += 1000 / 60) {
      now += 1000 / 60;
      const cb = queued;
      queued = null;
      cb?.(now);
    }
  };
  return {
    tw,
    run,
    shown: () => shown,
    setSpeed: (s: number) => {
      speed = s;
    },
  };
}

describe('Typewriter', () => {
  it('reveals text at the chosen pace, not all at once', () => {
    const { tw, run, shown } = setup(50);
    tw.push('x'.repeat(200));
    run(1000);
    expect(shown().length).toBeGreaterThanOrEqual(45);
    expect(shown().length).toBeLessThanOrEqual(55);
    run(5000);
    expect(shown()).toBe('x'.repeat(200));
  });

  it('shows everything per frame at instant speed', () => {
    const { tw, run, shown } = setup(charsPerSecond('instant'));
    tw.push('Hello, ');
    tw.push('world');
    run(20);
    expect(shown()).toBe('Hello, world');
  });

  it('applies a speed change mid-answer', () => {
    const { tw, run, shown, setSpeed } = setup(10);
    tw.push('y'.repeat(500));
    run(1000);
    const slow = shown().length;
    setSpeed(200);
    run(1000);
    expect(shown().length - slow).toBeGreaterThan(150);
  });

  it('types code blocks faster than prose', () => {
    const prose = setup(40);
    prose.tw.push('p'.repeat(400));
    prose.run(1000);

    const code = setup(40);
    code.tw.push('```\n' + 'c'.repeat(400));
    code.run(1000);
    expect(code.shown().length).toBeGreaterThan(prose.shown().length * 2);
  });

  it('finish() skips to the end and resolves drain()', async () => {
    const { tw, run, shown } = setup(20);
    tw.push('The whole answer.');
    run(100);
    const drained = tw.drain();
    tw.finish();
    await drained;
    expect(shown()).toBe('The whole answer.');
    tw.push(' More.');
    expect(shown()).toBe('The whole answer. More.');
  });

  it('drain() waits until the queue is empty', async () => {
    const { tw, run, shown } = setup(100);
    tw.push('z'.repeat(30));
    let done = false;
    const drained = tw.drain().then(() => {
      done = true;
    });
    run(100);
    await Promise.resolve();
    expect(done).toBe(false);
    run(1000);
    await drained;
    expect(done).toBe(true);
    expect(shown()).toHaveLength(30);
  });

  it('reset() drops queued text and dispose() releases waiters', async () => {
    const { tw, run, shown } = setup(10);
    tw.push('old draft');
    tw.reset();
    tw.push('new');
    run(2000);
    expect(shown()).toBe('new');

    tw.push('never shown');
    const drained = tw.drain();
    tw.dispose();
    await drained;
    run(2000);
    expect(shown()).toBe('new');
  });

  it('never splits an emoji across frames', () => {
    const { tw, run, shown } = setup(60);
    tw.push('a😀b😀c😀d');
    for (let i = 0; i < 20; i++) {
      run(1000 / 60);
      expect(shown()).not.toMatch(/[\ud800-\udbff]$/);
    }
    expect(shown()).toBe('a😀b😀c😀d');
  });
});
