import { useState, useEffect } from 'react';

/**
 * Custom hook to manage Recharts entrance animation.
 * It returns `true` initially, allowing the entrance animation to play,
 * and permanently switches to `false` after the given duration.
 * This prevents Recharts from re-playing animations on ResizeObserver events (e.g., sidebar toggling).
 * 
 * @param {number} durationMs The duration in milliseconds before animation is disabled.
 * @returns {boolean} Whether the chart should currently animate.
 */
export function useChartAnimation(durationMs = 800) {
  const [shouldAnimate, setShouldAnimate] = useState(true);

  useEffect(() => {
    // Disable animation permanently after the default Recharts entrance duration completes
    const timer = setTimeout(() => {
      setShouldAnimate(false);
    }, durationMs);

    return () => clearTimeout(timer);
  }, [durationMs]);

  return shouldAnimate;
}
