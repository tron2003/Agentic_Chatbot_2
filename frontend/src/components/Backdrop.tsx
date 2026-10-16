import { motion, useTransform, type MotionValue } from 'motion/react';
import { useParallax } from '@/hooks/parallax';

/**
 * Three depth layers behind the whole app, moved by pointer and by message
 * scroll at different rates:
 *   far  – a field of station dots (wraps, so it scrolls forever)
 *   mid  – faint transit lines in the three route colours
 *   near – soft colour glows
 */

const TILE = 28;

function useLayer(depth: number, scrollMode: { kind: 'wrap'; rate: number } | { kind: 'ease'; amp: number }) {
  const { px, py, scroll, reduced } = useParallax();
  const range = 40 * depth;
  const x = useTransform(px, (v) => (reduced ? 0 : v * range));
  const y = useTransform([py, scroll] as MotionValue<number>[], ([p, s]: number[]) => {
    if (reduced) return 0;
    const drift =
      scrollMode.kind === 'wrap'
        ? -((s * scrollMode.rate) % TILE)
        : -scrollMode.amp * Math.tanh(s / 1400);
    return p * range * 0.6 + drift;
  });
  return { x, y };
}

export function Backdrop() {
  const far = useLayer(0.12, { kind: 'wrap', rate: 0.12 });
  const mid = useLayer(0.4, { kind: 'ease', amp: 140 });
  const near = useLayer(1, { kind: 'ease', amp: 300 });

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 overflow-hidden">
      {/* near: glows */}
      <motion.div style={near} className="absolute -inset-[15%]">
        <div
          className="absolute left-[8%] top-[4%] h-[46vmax] w-[46vmax] rounded-full blur-[90px]"
          style={{ background: 'var(--route-chat)', opacity: 'var(--glow-opacity)' }}
        />
        <div
          className="absolute right-[2%] top-[38%] h-[38vmax] w-[38vmax] rounded-full blur-[90px]"
          style={{ background: 'var(--route-agent)', opacity: 'calc(var(--glow-opacity) * 0.85)' }}
        />
        <div
          className="absolute bottom-[-6%] left-[30%] h-[30vmax] w-[30vmax] rounded-full blur-[100px]"
          style={{ background: 'var(--route-docs)', opacity: 'calc(var(--glow-opacity) * 0.55)' }}
        />
      </motion.div>

      {/* far: station dots */}
      <motion.div
        style={{
          ...far,
          backgroundImage: 'radial-gradient(circle, var(--dot) 1.1px, transparent 1.6px)',
          backgroundSize: `${TILE}px ${TILE}px`,
          maskImage: 'radial-gradient(ellipse 75% 70% at 50% 40%, black 30%, transparent 85%)',
          WebkitMaskImage: 'radial-gradient(ellipse 75% 70% at 50% 40%, black 30%, transparent 85%)',
        }}
        className="absolute -inset-[60px]"
      />

      {/* mid: transit lines */}
      <motion.svg
        style={{
          ...mid,
          maskImage: 'radial-gradient(ellipse 38% 46% at 50% 52%, transparent 35%, black 80%)',
          WebkitMaskImage: 'radial-gradient(ellipse 38% 46% at 50% 52%, transparent 35%, black 80%)',
        }}
        className="absolute -inset-[10%] h-[120%] w-[120%]"
        viewBox="0 0 1440 900"
        preserveAspectRatio="xMidYMid slice"
        fill="none"
      >
        <g strokeWidth="1.4" strokeLinecap="round" opacity="0.32">
          <path d="M-40 180 C 260 180, 380 300, 620 300 S 1040 160, 1500 170" stroke="var(--route-chat)" />
          <path d="M-40 560 C 300 560, 420 420, 720 430 S 1100 600, 1500 590" stroke="var(--route-agent)" />
          <path d="M180 960 C 220 760, 420 700, 640 700 S 980 820, 1120 960" stroke="var(--route-docs)" />
        </g>
        <g strokeWidth="1.6" opacity="0.5">
          {[
            [620, 300, 'chat'],
            [1040, 196, 'chat'],
            [300, 520, 'agent'],
            [720, 430, 'agent'],
            [1180, 560, 'agent'],
            [640, 700, 'docs'],
          ].map(([cx, cy, r]) => (
            <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="4.5" fill="var(--bg)" stroke={`var(--route-${r})`} />
          ))}
        </g>
      </motion.svg>

      {/* readability scrim so text never sits on a busy patch */}
      <div
        className="absolute inset-0"
        style={{ background: 'radial-gradient(ellipse 60% 70% at 50% 45%, color-mix(in oklab, var(--bg) 55%, transparent), transparent 80%)' }}
      />
    </div>
  );
}
