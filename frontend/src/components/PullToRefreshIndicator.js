import { Loader2, ArrowDown } from 'lucide-react';

/**
 * Visual indicator for a pull-to-refresh gesture (iter 317).
 * Shown above the list while the user pulls; flips into a spinning state
 * once the refresh handler is running.
 *
 * Mounted as a sibling above the scrollable list. Its outer wrapper grows
 * in height as the user pulls, so the list content gets pushed down
 * naturally without absolute positioning headaches.
 */
export default function PullToRefreshIndicator({ pullPx, refreshing, threshold }) {
  const visible = pullPx > 0 || refreshing;
  const progress = Math.min(pullPx / threshold, 1);
  return (
    <div
      data-testid="ptr-indicator"
      style={{ height: refreshing ? Math.max(pullPx, 48) : pullPx, transition: refreshing ? 'height 200ms ease-out' : undefined }}
      className="md:hidden overflow-hidden flex items-end justify-center"
      aria-hidden={!visible}
    >
      {visible && (
        <div className="pb-2 flex flex-col items-center gap-1 text-[#4A5D4E]">
          {refreshing ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <ArrowDown
              className="w-5 h-5 transition-transform"
              style={{ transform: `rotate(${progress >= 1 ? 180 : 0}deg)` }}
            />
          )}
          <span className="text-[10px] text-[#6B7280]">
            {refreshing
              ? 'Aktualisiere…'
              : progress >= 1
                ? 'Loslassen zum Aktualisieren'
                : 'Ziehen zum Aktualisieren'}
          </span>
        </div>
      )}
    </div>
  );
}
