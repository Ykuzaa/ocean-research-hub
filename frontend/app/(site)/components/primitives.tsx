import Link from "next/link";
import type { ReactNode } from "react";
import type { LandingData, LandingStatus } from "@/app/lib/landing";

/** Small mono over-line. The landing's only all-caps text. */
export function Kicker({ children }: { children: ReactNode }) {
  return (
    <p className="font-mono text-[0.6875rem] uppercase tracking-[0.22em] text-tide-500">{children}</p>
  );
}

export function SectionHeader({
  kicker,
  title,
  lede,
}: {
  kicker: string;
  title: ReactNode;
  lede?: ReactNode;
}) {
  return (
    <div className="max-w-2xl">
      <Kicker>{kicker}</Kicker>
      <h2 className="mt-3 font-display text-[1.75rem] font-normal leading-[1.15] tracking-[-0.01em] text-ink-900 sm:text-4xl">
        {title}
      </h2>
      {lede && <p className="mt-3 text-[0.9375rem] leading-relaxed text-ink-600 sm:text-base">{lede}</p>}
    </div>
  );
}

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-rule bg-sheet-2 ${className}`}>{children}</div>
  );
}

/** Monospaced key/value chip used for pages, sections and statuses. */
export function MetaChip({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "accent" }) {
  const tones = {
    neutral: "border-rule text-ink-400",
    accent: "border-tide-500/40 text-tide-500",
  };
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded border px-1.5 py-0.5 font-mono text-[0.6875rem] leading-4 ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

/**
 * Horizontal magnitude bar: one hue, grows from a shared baseline, 4px rounded
 * data end, value direct-labelled at the tip. No legend — a single series.
 */
export function MagnitudeRow({
  label,
  value,
  max,
  suffix,
}: {
  label: string;
  value: number;
  max: number;
  suffix?: string;
}) {
  const share = max > 0 ? Math.max(value / max, 0.02) : 0;
  return (
    <div className="grid grid-cols-[minmax(4.5rem,9rem)_minmax(0,1fr)_auto] items-center gap-3 sm:gap-4">
      <span className="truncate text-[0.8125rem] text-ink-600">{label}</span>
      <span className="h-2.5 min-w-0 bg-sheet-3">
        <span
          className="block h-full rounded-r-[4px] bg-tide-400"
          style={{ width: `${share * 100}%` }}
        />
      </span>
      <span className="w-14 text-right font-mono text-xs tabular-nums text-ink-900">
        {value}
        {suffix && <span className="text-ink-400">{suffix}</span>}
      </span>
    </div>
  );
}

export function StatTile({ value, label, hint }: { value: string; label: string; hint?: string }) {
  return (
    <div>
      <p className="font-sans text-2xl font-semibold text-ink-900 sm:text-[1.75rem]">{value}</p>
      <p className="mt-1 text-[0.8125rem] font-medium text-ink-600">{label}</p>
      {hint && <p className="mt-1 text-xs leading-relaxed text-ink-400">{hint}</p>}
    </div>
  );
}

/**
 * Shown in place of a figure. An outage, an empty corpus and a corpus that
 * simply has no qualifying data are three different things, and saying the
 * wrong one misdiagnoses the system for the reader.
 */
export function PanelPlaceholder({
  what,
  status,
  empty,
}: {
  what: string;
  status: LandingStatus;
  /** Overrides the "ready but nothing qualifies" wording. */
  empty?: string;
}) {
  const message =
    status === "unavailable"
      ? `${what} comes from the live corpus. The corpus API is not responding — reload once it is back up.`
      : status === "empty"
        ? `${what} will appear once the corpus holds its first paper.`
        : (empty ?? `${what} has no qualifying data in the corpus yet.`);

  return (
    <p
      role={status === "unavailable" ? "status" : undefined}
      className="rounded border border-dashed border-rule px-4 py-6 text-center text-[0.8125rem] text-ink-400"
    >
      {message}
    </p>
  );
}

/** States that the figures on screen describe less than the whole corpus. */
export function PartialNotice({ partial }: { partial: NonNullable<LandingData["partial"]> }) {
  const reasons = [
    partial.truncatedAt !== null
      ? `counted over the ${partial.truncatedAt} most recently updated papers`
      : null,
    partial.missingRecords > 0
      ? `${partial.missingRecords} record${partial.missingRecords === 1 ? "" : "s"} could not be read`
      : null,
  ].filter(Boolean);

  return (
    <p
      role="status"
      className="mt-6 rounded border border-dashed border-rule bg-sheet-2 px-4 py-3 text-[0.8125rem] leading-relaxed text-ink-400"
    >
      Partial view: {reasons.join("; ")}. The figures below describe that subset, not the whole
      corpus.
    </p>
  );
}

export function Cta({
  href,
  children,
  variant = "primary",
}: {
  href: string;
  children: ReactNode;
  variant?: "primary" | "ghost";
}) {
  const base =
    "inline-flex w-full items-center justify-center gap-2 rounded px-5 py-2.5 sm:w-auto text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tide-600 focus-visible:ring-offset-2 focus-visible:ring-offset-sheet-0";
  const variants = {
    primary: "bg-tide-600 text-white hover:bg-tide-500",
    ghost: "border border-rule bg-sheet-2 text-ink-900 hover:border-tide-500 hover:text-tide-600",
  };
  const className = `${base} ${variants[variant]}`;

  // In-page anchors stay plain anchors; Link is for route navigation.
  return href.startsWith("#") ? (
    <a href={href} className={className}>
      {children}
    </a>
  ) : (
    <Link href={href} className={className}>
      {children}
    </Link>
  );
}
