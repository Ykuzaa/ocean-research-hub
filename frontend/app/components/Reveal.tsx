import type { ReactNode } from "react";

/**
 * Fades content up as it scrolls into view. Pure CSS (see `.reveal` in
 * globals.css): content is never hidden waiting for JavaScript, and browsers
 * without scroll-driven animations play it once on load instead.
 */
export function Reveal({ children, delay = 0, className = "" }: { children: ReactNode; delay?: number; className?: string }) {
  return (
    <div style={{ animationDelay: `${delay}ms` }} className={`reveal ${className}`}>
      {children}
    </div>
  );
}
