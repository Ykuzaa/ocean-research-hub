import { contourPath } from "@/app/lib/contours";

/**
 * Ocean Research Hub mark: a crop of a bathymetric chart — three isobaths
 * around an off-centre high, cut by a satellite ground track. The summit sits
 * low and right so the outer contours run off the frame and the mark reads as
 * a detail of a larger chart rather than as a target.
 *
 * Same relief field the landing hero draws at full size. Strokes use
 * `currentColor`, so one mark serves the dark public surface and the light
 * workspace.
 */
const LEVELS = [
  { level: 17, opacity: 0.32 },
  { level: 11, opacity: 0.62 },
  { level: 5.8, opacity: 1 },
];

export function BrandMark({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
      <clipPath id="brand-mark-clip">
        <rect x="0" y="0" width="24" height="24" />
      </clipPath>
      <g clipPath="url(#brand-mark-clip)" stroke="currentColor" strokeWidth="1.5">
        {LEVELS.map(({ level, opacity }, index) => (
          <path
            key={level}
            d={contourPath({
              cx: 15,
              cy: 15.5,
              level,
              index,
              samples: 11,
              drift: 0.35,
              smooth: true,
              precision: 2,
            })}
            strokeOpacity={opacity}
          />
        ))}
        <path d="M-2 21L26 3" strokeOpacity="0.7" strokeDasharray="2.4 2.4" strokeLinecap="round" />
      </g>
    </svg>
  );
}

export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`whitespace-nowrap font-semibold tracking-tight ${className}`}>
      Ocean Research Hub
    </span>
  );
}
