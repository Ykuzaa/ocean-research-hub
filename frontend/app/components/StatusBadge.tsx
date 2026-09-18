import type { WorkflowStatus } from "@/app/lib/api";

const STYLES: Record<WorkflowStatus, string> = {
  INGESTED: "bg-slate-100 text-slate-700 ring-slate-300",
  PARSED: "bg-slate-100 text-slate-700 ring-slate-300",
  EXTRACTED: "bg-sky-100 text-sky-800 ring-sky-300",
  SCIENTIFIC_AUDIT: "bg-amber-100 text-amber-800 ring-amber-300",
  VERIFIED: "bg-emerald-100 text-emerald-800 ring-emerald-300",
  PARTIAL: "bg-amber-100 text-amber-800 ring-amber-300",
  REJECTED: "bg-rose-100 text-rose-800 ring-rose-300",
};

const LABELS: Record<WorkflowStatus, string> = {
  INGESTED: "Ingested",
  PARSED: "Parsed",
  EXTRACTED: "Extracted (pending audit)",
  SCIENTIFIC_AUDIT: "Under audit",
  VERIFIED: "Verified",
  PARTIAL: "Partially verified",
  REJECTED: "Rejected",
};

export function StatusBadge({ status }: { status: WorkflowStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${STYLES[status]}`}
    >
      {LABELS[status]}
    </span>
  );
}
