import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react';
import { useMotionValue, useReducedMotion, useSpring, useTransform, type MotionValue } from 'motion/react';

/**
 * Shared parallax inputs:
 *  - pointer: -1..1 on each axis, eased with a spring
 *  - scroll: pixels scrolled in the active scroll container (the message list)
 * Layers turn these into transforms with `useDepth(depth)`.
 */
interface ParallaxInputs {
  px: MotionValue<number>;
  py: MotionValue<number>;
  scroll: MotionValue<number>;
  reduced: boolean;
}

const ParallaxCtx = createContext<ParallaxInputs | null>(null);

export function ParallaxProvider({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion() ?? false;
  const rawX = useMotionValue(0);
  const rawY = useMotionValue(0);
  const scroll = useMotionValue(0);
  const px = useSpring(rawX, { stiffness: 60, damping: 18, mass: 0.6 });
  const py = useSpring(rawY, { stiffness: 60, damping: 18, mass: 0.6 });

  useEffect(() => {
    if (reduced) return;
    const coarse = window.matchMedia('(pointer: coarse)').matches;
    if (coarse) return; // touch devices: scroll parallax only
    const onMove = (e: PointerEvent) => {
      rawX.set((e.clientX / window.innerWidth) * 2 - 1);
      rawY.set((e.clientY / window.innerHeight) * 2 - 1);
    };
    const onLeave = () => {
      rawX.set(0);
      rawY.set(0);
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    document.addEventListener('pointerleave', onLeave);
    return () => {
      window.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerleave', onLeave);
    };
  }, [reduced, rawX, rawY]);

  const value = useMemo(() => ({ px, py, scroll, reduced }), [px, py, scroll, reduced]);
  return <ParallaxCtx.Provider value={value}>{children}</ParallaxCtx.Provider>;
}

export function useParallax() {
  const ctx = useContext(ParallaxCtx);
  if (!ctx) throw new Error('useParallax must be used inside <ParallaxProvider>');
  return ctx;
}

/**
 * Translate for a layer at `depth` (0 = fixed, 1 = moves with the pointer most).
 * `scrollRate` is how fast the layer drifts relative to content scroll
 * (content moves at 1.0, so 0.1 reads as far away).
 */
export function useDepth(depth: number, scrollRate = 0) {
  const { px, py, scroll, reduced } = useParallax();
  const range = 42 * depth;
  const x = useTransform(px, (v) => (reduced ? 0 : v * range));
  const y = useTransform([py, scroll] as MotionValue<number>[], ([p, s]: number[]) =>
    reduced ? 0 : p * range * 0.6 - s * scrollRate,
  );
  return { x, y };
}

/** Feed a scroll container's position into the parallax system. */
export function useScrollParallax(ref: React.RefObject<HTMLElement | null>) {
  const { scroll, reduced } = useParallax();
  useEffect(() => {
    const el = ref.current;
    if (!el || reduced) return;
    const onScroll = () => scroll.set(el.scrollTop);
    onScroll();
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      el.removeEventListener('scroll', onScroll);
      scroll.set(0);
    };
  }, [ref, scroll, reduced]);
}
