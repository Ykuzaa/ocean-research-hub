import {
  BookOpen,
  Bot,
  Brain,
  ChartColumn,
  Compass,
  Cpu,
  Fish,
  Flame,
  Globe,
  Layers,
  Leaf,
  Mountain,
  Satellite,
  SatelliteDish,
  SlidersHorizontal,
  Snowflake,
  Thermometer,
  Tornado,
  Waves,
  type LucideIcon,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  forecasting: Globe,
  benchmarks: ChartColumn,
  "data-assimilation": Satellite,
  subsurface: Layers,
  sst: Thermometer,
  "ssh-altimetry": SatelliteDish,
  "neural-operators": Cpu,
  parameterization: SlidersHorizontal,
  currents: Compass,
  "eddies-fronts": Tornado,
  "marine-heatwaves": Flame,
  "sea-ice": Snowflake,
  waves: Waves,
  biogeochemistry: Leaf,
  bathymetry: Mountain,
  "foundation-models": Brain,
  "llm-agents": Bot,
  "marine-ecology": Fish,
  reviews: BookOpen,
};

export function DomainIcon({ id, className }: { id: string; className?: string }) {
  const Icon = ICONS[id] ?? Globe;
  return <Icon aria-hidden className={className} strokeWidth={1.75} />;
}

// Literal class strings so Tailwind generates them; cycled for gentle variety.
const ACCENTS = [
  { badge: "bg-cyan-50 text-cyan-700 ring-cyan-100", hover: "group-hover:bg-cyan-600 group-hover:text-white group-hover:ring-cyan-600" },
  { badge: "bg-sky-50 text-sky-700 ring-sky-100", hover: "group-hover:bg-sky-600 group-hover:text-white group-hover:ring-sky-600" },
  { badge: "bg-teal-50 text-teal-700 ring-teal-100", hover: "group-hover:bg-teal-600 group-hover:text-white group-hover:ring-teal-600" },
  { badge: "bg-blue-50 text-blue-700 ring-blue-100", hover: "group-hover:bg-blue-600 group-hover:text-white group-hover:ring-blue-600" },
  { badge: "bg-indigo-50 text-indigo-700 ring-indigo-100", hover: "group-hover:bg-indigo-600 group-hover:text-white group-hover:ring-indigo-600" },
];

export function accentFor(index: number) {
  return ACCENTS[index % ACCENTS.length];
}
