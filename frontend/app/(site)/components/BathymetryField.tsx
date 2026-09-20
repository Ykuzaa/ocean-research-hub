import { contourPath } from "@/app/lib/contours";

/**
 * The landing's signature visual: a bathymetric contour field crossed by two
 * satellite ground tracks, with the stations sampled along them marked.
 *
 * Same relief field as the brand mark, drawn at full size.
 */

const VIEW = 420;
const CENTRE = { x: 210, y: 208 };
const LEVELS = [230, 195, 162, 132, 104, 78, 54, 32];

/** Two satellite ground tracks, and the stations sampled along them. */
const TRACK_A = { x1: -30, y1: 366, x2: 450, y2: 30 };
const TRACK_B = { x1: -30, y1: 82, x2: 450, y2: 398 };

function along(track: typeof TRACK_A, t: number) {
  return { x: track.x1 + (track.x2 - track.x1) * t, y: track.y1 + (track.y2 - track.y1) * t };
}

const STATIONS = [
  { ...along(TRACK_A, 0.2), r: 3 },
  { ...along(TRACK_A, 0.33), r: 3.4 },
  { ...along(TRACK_A, 0.4356), r: 4.8 }, // where the two tracks cross
  { ...along(TRACK_A, 0.6), r: 3.4 },
  { ...along(TRACK_A, 0.76), r: 3 },
  { ...along(TRACK_B, 0.24), r: 3 },
  { ...along(TRACK_B, 0.63), r: 3.4 },
  { ...along(TRACK_B, 0.83), r: 3 },
];

export function BathymetryField({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox={`0 0 ${VIEW} ${VIEW}`}
      role="img"
      aria-label="Bathymetric contour field crossed by two satellite ground tracks, with the stations sampled along them marked."
      className={className}
    >
      <clipPath id="field-clip">
        <rect x="0" y="0" width={VIEW} height={VIEW} rx="8" />
      </clipPath>

      <g clipPath="url(#field-clip)">
        <rect x="0" y="0" width={VIEW} height={VIEW} className="fill-sheet-2" />

        {/* Measurement lattice */}
        <g stroke="#0e1a22" strokeOpacity="0.06" strokeWidth="1">
          {Array.from({ length: 8 }, (_, i) => (
            <line key={`v${i}`} x1={(i + 1) * 48} y1="0" x2={(i + 1) * 48} y2={VIEW} />
          ))}
          {Array.from({ length: 8 }, (_, i) => (
            <line key={`h${i}`} x1="0" y1={(i + 1) * 48} x2={VIEW} y2={(i + 1) * 48} />
          ))}
        </g>

        {/* Isobaths, deepest first so the summit reads brightest */}
        {LEVELS.map((level, index) => (
          <path
            key={level}
            d={contourPath({ cx: CENTRE.x, cy: CENTRE.y, level, index, drift: 3 })}
            fill="none"
            pathLength={1}
            stroke="#1f8fa6"
            strokeOpacity={0.38 + index * 0.08}
            strokeWidth={index >= LEVELS.length - 2 ? 1.6 : 1.2}
            className="contour-trace"
            style={{ animationDelay: `${index * 100}ms` }}
          />
        ))}

        {/* Satellite ground tracks */}
        <g fill="none" strokeLinecap="round">
          <line
            x1={TRACK_A.x1}
            y1={TRACK_A.y1}
            x2={TRACK_A.x2}
            y2={TRACK_A.y2}
            stroke="#0e5163"
            strokeOpacity="0.7"
            strokeWidth="1.5"
            strokeDasharray="5 10"
            className="track-sweep"
          />
          <line
            x1={TRACK_B.x1}
            y1={TRACK_B.y1}
            x2={TRACK_B.x2}
            y2={TRACK_B.y2}
            stroke="#0e5163"
            strokeOpacity="0.38"
            strokeWidth="1.5"
            strokeDasharray="5 10"
            className="track-sweep track-sweep-slow"
          />
        </g>

        {STATIONS.map((station) => (
          <circle
            key={`${station.x.toFixed(1)}-${station.y.toFixed(1)}`}
            cx={station.x}
            cy={station.y}
            r={station.r}
            className="fill-tide-500"
            stroke="#ffffff"
            strokeWidth="2.5"
          />
        ))}

        {/* Depth annotations, the way a chart labels its isobaths */}
        <g className="fill-ink-400 font-mono" fontSize="9.5" letterSpacing="0.08em">
          <text x="16" y="26">
            0 m
          </text>
          <text x="16" y="406">
            −4000 m
          </text>
          <text x={VIEW - 88} y="406">
            TRACK 02
          </text>
        </g>
      </g>

      <rect
        x="0.5"
        y="0.5"
        width={VIEW - 1}
        height={VIEW - 1}
        rx="8"
        fill="none"
        stroke="#dbe4ea"
        strokeWidth="1"
      />
    </svg>
  );
}
