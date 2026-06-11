import { useEffect, useRef, useState } from 'react';

/**
 * Pull-to-refresh primitive for native-feeling mobile list refresh.
 *
 * Usage:
 *   const { pullPx, refreshing, isPulling, bind, threshold } = usePullToRefresh({
 *     onRefresh: () => loadData(),
 *   });
 *   // attach <PullToRefreshIndicator pullPx={pullPx} refreshing={refreshing} ... />
 *   // wrap target with <div {...bind}> ... </div>
 *
 * Activates only when:
 *   - viewport is < 768 px (the indicator is hidden on desktop)
 *   - the scroll container is at the very top (preventing accidental
 *     pulls mid-scroll)
 *   - the gesture is mostly vertical (>1.5x horizontal component)
 *
 * Uses Pointer Events so it works on iOS Safari, Chrome Android and
 * any modern desktop. Pull resistance: linear up to 40px, then 0.6x
 * decay so the gesture feels rubbery beyond the threshold.
 */
const DEFAULTS = {
  threshold: 70,
  maxPull: 130,
  enabledMaxWidth: 767,
};

export default function usePullToRefresh({ onRefresh, threshold = DEFAULTS.threshold, maxPull = DEFAULTS.maxPull }) {
  const [pullPx, setPullPx] = useState(0);
  const [isPulling, setIsPulling] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const startRef = useRef({ y: 0, x: 0, active: false });

  // Find the closest scrollable ancestor so we only engage when at scrollTop=0
  const getScrollEl = (el) => {
    let node = el;
    while (node && node !== document.body) {
      const overflowY = getComputedStyle(node).overflowY;
      if (overflowY === 'auto' || overflowY === 'scroll') return node;
      node = node.parentElement;
    }
    return document.scrollingElement || document.documentElement;
  };

  useEffect(() => {
    // Reset when the consumer remounts (e.g. route change)
    return () => {
      setPullPx(0);
      setIsPulling(false);
      setRefreshing(false);
    };
  }, []);

  const onPointerDown = (e) => {
    if (typeof window !== 'undefined' && window.innerWidth > DEFAULTS.enabledMaxWidth) return;
    if (refreshing) return;
    const scrollEl = getScrollEl(e.currentTarget);
    if ((scrollEl?.scrollTop ?? 0) > 0) return;
    startRef.current = { y: e.clientY, x: e.clientX, active: true };
  };

  const onPointerMove = (e) => {
    const s = startRef.current;
    if (!s.active || refreshing) return;
    const dy = e.clientY - s.y;
    const dx = Math.abs(e.clientX - s.x);
    // Mostly horizontal? — abort, let the page handle the gesture.
    if (dy <= 0 || dx > Math.abs(dy) * 1.5) {
      s.active = false;
      setIsPulling(false);
      setPullPx(0);
      return;
    }
    setIsPulling(true);
    // Linear up to threshold, then 0.6x resistance.
    const eased = dy <= threshold ? dy : threshold + (dy - threshold) * 0.6;
    setPullPx(Math.min(eased, maxPull));
  };

  const onPointerUp = async () => {
    const s = startRef.current;
    s.active = false;
    if (refreshing) return;
    if (pullPx >= threshold && onRefresh) {
      setRefreshing(true);
      setPullPx(threshold);
      try { await onRefresh(); } finally {
        setRefreshing(false);
        setPullPx(0);
        setIsPulling(false);
      }
    } else {
      setPullPx(0);
      setIsPulling(false);
    }
  };

  return {
    pullPx,
    refreshing,
    isPulling,
    threshold,
    bind: {
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel: onPointerUp,
    },
  };
}
