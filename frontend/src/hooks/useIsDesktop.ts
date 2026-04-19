/**
 * `useIsDesktop` -- listens to the `(min-width: 1024px)` media query
 * and re-renders when the viewport crosses the breakpoint.
 *
 * Used by `<ScenarioPage>` to switch between the three-column
 * desktop layout and the single-column stacked mobile layout. The
 * Tailwind `lg:*` utilities apply the styling, but driving it from
 * JS too lets us expose a `data-layout` attribute that tests can
 * assert against.
 */

import { useEffect, useState } from "react";

const QUERY = "(min-width: 1024px)";

/** Returns true when the viewport is at or above 1024 px. */
export function useIsDesktop(): boolean {
  const [isDesktop, setIsDesktop] = useState<boolean>(() => {
    if (typeof window === "undefined" || !window.matchMedia) return true;
    return window.matchMedia(QUERY).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia(QUERY);
    const onChange = () => setIsDesktop(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return isDesktop;
}
