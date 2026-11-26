import { motion, useTransform, type MotionValue } from 'motion/react';
import { useParallax } from '@/hooks/parallax';
import type { Route } from '@/lib/types';

/**
 * The hero: the actual routing graph this app runs, drawn as a transit map.
 * Node positions are motion values driven by the pointer, so nearer nodes
 * move more than the junction and the branches bend with them (parallax in
 * the graph itself, not just behind it).
 */

const ORIGIN = { x: 40, y: 110 };
const JUNCTION = { x: 190, y: 110 };
const DEST: Record<Route, { x: number; y: number }> = {
  chat: { x: 452, y: 34 },
  rag: { x: 470, y: 110 },
  agent: { x: 452, y: 186 },
};
const ORDER: Route[] = ['chat', 'rag', 'agent'];
const COLOR: Record<Route, string> = { chat: 'var(--route-chat)', rag: 'var(--route-docs)', agent: 'var(--route-agent)' };

function useNode(base: { x: number; y: number }, depth: number) {
  const { px, py, reduced } = useParallax();
  const x = useTransform(px, (v) => base.x + (reduced ? 0 : v * 26 * depth));
  const y = useTransform(py, (v) => base.y + (reduced ? 0 : v * 16 * depth));
  return { x, y };
}

function branchPath(j: { x: number; y: number }, d: { x: number; y: number }) {
  const midX = j.x + (d.x - j.x) * 0.45;
  return `M ${j.x} ${j.y} C ${midX} ${j.y}, ${midX} ${d.y}, ${d.x} ${d.y}`;
}

interface Props {
  highlight: Route | null;
  descriptions: Record<Route, string>;
  labels: Record<Route, string>;
}

export function RouteMap({ highlight, descriptions, labels }: Props) {
  const { reduced } = useParallax();
  const origin = useNode(ORIGIN, 0.15);
  const junction = useNode(JUNCTION, 0.3);
  const dests = {
    chat: useNode(DEST.chat, 1),
    rag: useNode(DEST.rag, 0.75),
    agent: useNode(DEST.agent, 1.15),
  } satisfies Record<Route, { x: MotionValue<number>; y: MotionValue<number> }>;

  const trunk = useTransform(
    [origin.x, origin.y, junction.x, junction.y] as MotionValue<number>[],
    ([ox, oy, jx, jy]: number[]) => `M ${ox} ${oy} L ${jx} ${jy}`,
  );
  const branches = {
    chat: useTransform([junction.x, junction.y, dests.chat.x, dests.chat.y] as MotionValue<number>[], ([a, b, c, d]: number[]) =>
      branchPath({ x: a, y: b }, { x: c, y: d }),
    ),
    rag: useTransform([junction.x, junction.y, dests.rag.x, dests.rag.y] as MotionValue<number>[], ([a, b, c, d]: number[]) =>
      branchPath({ x: a, y: b }, { x: c, y: d }),
    ),
    agent: useTransform([junction.x, junction.y, dests.agent.x, dests.agent.y] as MotionValue<number>[], ([a, b, c, d]: number[]) =>
      branchPath({ x: a, y: b }, { x: c, y: d }),
    ),
  };

  const originLabelY = useTransform(origin.y, (v) => v + 28);
  const junctionLabelY = useTransform(junction.y, (v) => v + 34);

  return (
    <svg
      viewBox="0 0 600 220"
      className="h-auto w-full max-w-[600px] overflow-visible"
      role="img"
      aria-label="Each question enters a router that sends it to Chat, Documents or Deep research."
    >
      {/* trunk */}
      <motion.path
        d={trunk}
        stroke="var(--line-strong)"
        strokeWidth={3}
        strokeLinecap="round"
        fill="none"
        initial={reduced ? false : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      />

      {ORDER.map((r, i) => {
        const active = highlight === r;
        const dimmed = highlight !== null && !active;
        return (
          <g key={r} style={{ transition: 'opacity 250ms ease' }} opacity={dimmed ? 0.35 : 1}>
            <motion.path
              d={branches[r]}
              stroke={COLOR[r]}
              strokeWidth={active ? 4 : 3}
              strokeLinecap="round"
              fill="none"
              initial={reduced ? false : { pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 0.7, delay: 0.45 + i * 0.15, ease: [0.3, 0.7, 0.2, 1] }}
            />
            {/* travelling signal */}
            {!reduced && (
              <motion.path
                d={branches[r]}
                stroke="var(--text)"
                strokeWidth={active ? 2.2 : 1.6}
                strokeLinecap="round"
                fill="none"
                pathLength={1}
                strokeDasharray="0.06 1"
                initial={{ strokeDashoffset: 1.06, opacity: 0 }}
                animate={{ strokeDashoffset: [1.06, 0], opacity: [0, 0.95, 0.95, 0] }}
                transition={{
                  duration: active ? 1.1 : 2.4,
                  delay: 1.5 + i * 0.8,
                  repeat: Infinity,
                  repeatDelay: active ? 0.15 : 2.6,
                  ease: 'easeInOut',
                }}
              />
            )}
          </g>
        );
      })}

      {/* origin */}
      <motion.circle cx={origin.x} cy={origin.y} r={7} fill="var(--text)" />
      <motion.text x={origin.x} y={originLabelY} textAnchor="middle" className="fill-[var(--text-muted)] text-[12px]">
        You
      </motion.text>

      {/* junction (the router) */}
      <motion.circle cx={junction.x} cy={junction.y} r={13} fill="var(--bg)" stroke="var(--text)" strokeWidth={3} />
      <motion.circle cx={junction.x} cy={junction.y} r={4.5} fill="var(--text)" />
      <motion.text x={junction.x} y={junctionLabelY} textAnchor="middle" className="fill-[var(--text-muted)] text-[12px]">
        Router
      </motion.text>

      {/* destinations */}
      {ORDER.map((r) => (
        <DestNode
          key={`node-${r}`}
          x={dests[r].x}
          y={dests[r].y}
          color={COLOR[r]}
          label={labels[r]}
          description={descriptions[r]}
          active={highlight === r}
          dimmed={highlight !== null && highlight !== r}
        />
      ))}
    </svg>
  );
}

function DestNode({ x, y, color, label, description, active, dimmed }: {
  x: MotionValue<number>;
  y: MotionValue<number>;
  color: string;
  label: string;
  description: string;
  active: boolean;
  dimmed: boolean;
}) {
  const textX = useTransform(x, (v) => v + 22);
  const labelY = useTransform(y, (v) => v - 2);
  const descY = useTransform(y, (v) => v + 15);
  return (
    <g opacity={dimmed ? 0.45 : 1} style={{ transition: 'opacity 250ms ease' }}>
      {active && <motion.circle cx={x} cy={y} r={20} fill={color} opacity={0.18} initial={{ scale: 0.6 }} animate={{ scale: 1 }} />}
      <motion.circle cx={x} cy={y} r={10} fill="var(--bg)" stroke={color} strokeWidth={3.5} />
      <motion.text x={textX} y={labelY} className="fill-[var(--text)] text-[15px] font-bold">
        {label}
      </motion.text>
      <motion.text x={textX} y={descY} className="fill-[var(--text-muted)] text-[12px]">
        {description}
      </motion.text>
    </g>
  );
}
