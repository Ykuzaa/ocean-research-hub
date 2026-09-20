import {
  PAPER_PAGE_LIMIT,
  getPaper,
  isAnalyzed,
  listDomains,
  listPaperPage,
  type Domain,
  type EvidenceField,
  type PaperRecord,
  type PaperSummary,
  type StoredPaper,
} from "@/app/lib/api";

/**
 * Everything the public landing states about the corpus is aggregated here,
 * from the live API, at request time. Three rules hold throughout:
 *
 * 1. A quote shown to the reader is always `source.evidence` — the verbatim
 *    sentence in the paper — never the normalised `value` the extractor
 *    derived from it. Both are carried so the page can show them side by side.
 * 2. Nothing is counted that lacks the provenance it is presented under.
 * 3. Failure, emptiness and partial results are distinct outcomes. A panel
 *    that cannot be computed says which of the three happened rather than
 *    showing a number nobody can trace.
 */

export type LandingStatus = "ready" | "empty" | "unavailable";

export type EvidenceItem = {
  paperId: string;
  paperTitle: string;
  /** Verbatim sentence from the paper. */
  evidence: string;
  /** The normalised value the extractor derived from that sentence. */
  claim: string;
  page: number | null;
  section: string | null;
  status: string;
  provenance: string | null;
};

export type LimitationTally = {
  key: string;
  label: string;
  papers: number;
  items: EvidenceItem[];
};

export type YearBar = { year: number; extracted: number; bibliographic: number };

export type SectionTally = { key: string; label: string; fields: number };

export type StatusTally = { status: string; fields: number; blurb: string };

export type NamedTally = { name: string; papers: number };

export type ExtractionRow = {
  label: string;
  value: string;
  status: string;
  provenance: string | null;
  page: number | null;
  section: string | null;
  evidence: string;
};

export type ExtractionDemo = {
  paperId: string;
  paperTitle: string;
  rows: ExtractionRow[];
};

export type ConflictExample = {
  paperId: string;
  paperTitle: string;
  label: string;
  values: string[];
};

export type LandingData = {
  status: LandingStatus;
  /** Set when some detail records could not be read; the figures are a subset. */
  partial: { missingRecords: number; truncatedAt: number | null } | null;
  totals: {
    papers: number;
    domains: number;
    papersWithFields: number;
    extractedFields: number;
    recordFields: number;
    sourcedValues: number;
    humanAudited: number;
  };
  statuses: StatusTally[];
  years: YearBar[];
  limitations: LimitationTally[];
  sections: SectionTally[];
  families: NamedTally[];
  datasets: NamedTally[];
  extraction: ExtractionDemo | null;
  conflict: ConflictExample | null;
};

/** Limitation families, in the order the record schema declares them. */
const LIMITATION_LABELS: Record<string, string> = {
  author_reported: "Stated by the authors",
  data: "Data",
  physics: "Physics",
  generalization: "Generalisation",
  uncertainty: "Uncertainty",
  compute: "Compute",
  reproducibility: "Reproducibility",
};

const SECTION_LABELS: Record<string, string> = {
  data: "Data",
  architecture: "Architecture",
  scientific_framing: "Scientific framing",
  training: "Training",
  results: "Results",
  evaluation: "Evaluation",
  limitations: "Limitations",
  objective: "Objective / loss",
};

/** Plain-language gloss for each verification state, shown next to its count. */
const STATUS_BLURBS: Record<string, string> = {
  EXTRACTION_ERROR: "the extractor could not ground this field at its expected location",
  NOT_VERIFIED: "extracted with a source sentence, not yet confirmed by a human auditor",
  NOT_REPORTED: "the paper does not state it, so the record does not either",
  CONFLICT: "two parts of the paper disagree; both readings are kept",
  PARTIALLY_VERIFIED: "confirmed in part by a human auditor",
  VERIFIED: "confirmed against the source by a human auditor",
};

const STATUS_ORDER = [
  "EXTRACTION_ERROR",
  "NOT_VERIFIED",
  "NOT_REPORTED",
  "CONFLICT",
  "PARTIALLY_VERIFIED",
  "VERIFIED",
];

const AUDITED_STATUSES = new Set(["VERIFIED", "PARTIALLY_VERIFIED"]);

/** The training fields the extraction walkthrough shows, in reading order. */
const EXTRACTION_FIELDS: { path: string; label: string }[] = [
  { path: "training.optimizer", label: "Optimizer" },
  { path: "training.learning_rate", label: "Learning rate" },
  { path: "training.batch_size", label: "Batch size" },
  { path: "training.epochs_or_steps", label: "Epochs" },
];

/** Only an author-reported fact may be shown under "evidence in the paper". */
const AUTHOR_FACT = "AUTHOR_REPORTED_FACT";
const AUTHOR_LIMITATION = "AUTHOR_REPORTED_LIMITATION";

function isEvidenceField(node: unknown): node is EvidenceField {
  return typeof node === "object" && node !== null && "status" in node && "source" in node;
}

function fieldAt(record: PaperRecord, path: string): EvidenceField | undefined {
  let node: unknown = record;
  for (const key of path.split(".")) {
    if (typeof node !== "object" || node === null) return undefined;
    node = (node as Record<string, unknown>)[key];
  }
  return isEvidenceField(node) ? node : undefined;
}

export function hasValue(field: EvidenceField | undefined): boolean {
  if (!field) return false;
  const { value } = field;
  if (value === null || value === undefined || value === "") return false;
  return !(Array.isArray(value) && value.length === 0);
}

export function formatValue(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => formatValue(item)).join(" · ");
  if (value === null || value === undefined) return "—";
  return String(value);
}

/** Every leaf evidence field of a record, keyed by its dotted path. */
function walkFields(record: PaperRecord): { path: string; field: EvidenceField }[] {
  const out: { path: string; field: EvidenceField }[] = [];
  const visit = (node: unknown, path: string) => {
    if (isEvidenceField(node)) {
      out.push({ path, field: node });
    } else if (typeof node === "object" && node !== null) {
      for (const [key, child] of Object.entries(node)) visit(child, path ? `${path}.${key}` : key);
    }
  };
  visit(record, "");
  return out;
}

function titleOf(paper: StoredPaper, fallback: string): string {
  const title = fieldAt(paper.record, "paper.title")?.value;
  return typeof title === "string" && title ? title : fallback;
}

function trim(text: string, max: number): string {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length <= max ? clean : `${clean.slice(0, max - 1).trimEnd()}…`;
}

/**
 * Reported limitations, by family. A field is only counted when it is an
 * author-reported limitation AND carries the sentence it was read from —
 * anything else cannot be presented as evidence from the paper.
 */
export function tallyLimitations(papers: StoredPaper[], summaries: PaperSummary[]): LimitationTally[] {
  const titles = new Map(summaries.map((paper) => [paper.id, paper.title ?? "Untitled"]));
  const tallies = new Map<string, LimitationTally>();

  for (const paper of papers) {
    const limitations = paper.record.limitations;
    if (typeof limitations !== "object" || limitations === null) continue;

    for (const [key, label] of Object.entries(LIMITATION_LABELS)) {
      const field = (limitations as Record<string, unknown>)[key];
      if (!isEvidenceField(field) || !hasValue(field)) continue;
      if (field.provenance_type !== AUTHOR_LIMITATION) continue;
      const evidence = field.source?.evidence;
      if (!evidence) continue;

      const tally = tallies.get(key) ?? { key, label, papers: 0, items: [] };
      tally.papers += 1;
      const first = Array.isArray(field.value) ? field.value[0] : field.value;
      tally.items.push({
        paperId: paper.id,
        paperTitle: titleOf(paper, titles.get(paper.id) ?? "Untitled"),
        evidence: trim(String(evidence), 260),
        claim: trim(formatValue(first), 200),
        page: field.source.page ?? null,
        section: field.source.section ?? null,
        status: field.status,
        provenance: field.provenance_type ?? null,
      });
      tallies.set(key, tally);
    }
  }

  return [...tallies.values()].sort((a, b) => b.papers - a.papers || a.label.localeCompare(b.label));
}

export function tallyYears(papers: PaperSummary[]): YearBar[] {
  const years = new Map<number, YearBar>();
  for (const paper of papers) {
    if (typeof paper.year !== "number") continue;
    const bar = years.get(paper.year) ?? { year: paper.year, extracted: 0, bibliographic: 0 };
    if (isAnalyzed(paper)) bar.extracted += 1;
    else bar.bibliographic += 1;
    years.set(paper.year, bar);
  }
  return [...years.values()].sort((a, b) => a.year - b.year);
}

export function tallySections(papers: StoredPaper[]): SectionTally[] {
  const counts = new Map<string, number>();
  for (const paper of papers) {
    for (const { path, field } of walkFields(paper.record)) {
      const section = path.split(".")[0];
      // `paper` is bibliography, not an extracted scientific finding.
      if (!(section in SECTION_LABELS) || !hasValue(field)) continue;
      counts.set(section, (counts.get(section) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([key, fields]) => ({ key, label: SECTION_LABELS[key], fields }))
    .sort((a, b) => b.fields - a.fields);
}

/**
 * The full verification-state distribution over every leaf field of every
 * record read. All states are reported, including the failures: hiding
 * EXTRACTION_ERROR would describe a cleaner corpus than the one that exists.
 */
export function tallyStatuses(papers: StoredPaper[]): StatusTally[] {
  const counts = new Map<string, number>();
  for (const paper of papers) {
    for (const { field } of walkFields(paper.record)) {
      counts.set(field.status, (counts.get(field.status) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([status, fields]) => ({ status, fields, blurb: STATUS_BLURBS[status] ?? "" }))
    .sort((a, b) => {
      const rank = STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status);
      return rank !== 0 ? rank : b.fields - a.fields;
    });
}

export function tallyEvidence(papers: StoredPaper[]) {
  let recordFields = 0;
  let sourcedValues = 0;
  let humanAudited = 0;
  for (const paper of papers) {
    for (const { field } of walkFields(paper.record)) {
      recordFields += 1;
      if (hasValue(field) && field.source?.evidence) sourcedValues += 1;
      if (AUDITED_STATUSES.has(field.status)) humanAudited += 1;
    }
  }
  return { recordFields, sourcedValues, humanAudited };
}

/** How many papers name each entry of a list-valued field. */
function tallyNamed(papers: StoredPaper[], path: string, max = 8): NamedTally[] {
  const counts = new Map<string, number>();
  for (const paper of papers) {
    const field = fieldAt(paper.record, path);
    if (!field || !hasValue(field)) continue;
    const values = Array.isArray(field.value) ? field.value : [field.value];
    for (const name of new Set(values.map((value) => trim(formatValue(value), 52)))) {
      counts.set(name, (counts.get(name) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([name, papersNaming]) => ({ name, papers: papersNaming }))
    .sort((a, b) => b.papers - a.papers || a.name.localeCompare(b.name))
    .slice(0, max);
}

export function tallyFamilies(papers: StoredPaper[]): NamedTally[] {
  return tallyNamed(papers, "architecture.family");
}

export function tallyDatasets(papers: StoredPaper[]): NamedTally[] {
  return tallyNamed(papers, "data.datasets");
}

/**
 * The extraction walkthrough. It reads a real record rather than a fixture,
 * and only accepts author-reported facts that carry their source sentence,
 * so what the page labels "evidence in the paper" always is exactly that.
 */
export function pickExtractionDemo(papers: StoredPaper[], summaries: PaperSummary[]): ExtractionDemo | null {
  const titles = new Map(summaries.map((paper) => [paper.id, paper.title ?? "Untitled"]));
  let best: ExtractionDemo | null = null;

  for (const paper of papers) {
    const rows: ExtractionRow[] = [];
    for (const { path, label } of EXTRACTION_FIELDS) {
      const field = fieldAt(paper.record, path);
      const evidence = field?.source?.evidence;
      if (!field || !hasValue(field) || !evidence) continue;
      if (field.provenance_type !== AUTHOR_FACT) continue;
      rows.push({
        label,
        value: formatValue(field.value),
        status: field.status,
        provenance: field.provenance_type ?? null,
        page: field.source.page ?? null,
        section: field.source.section ?? null,
        evidence: trim(evidence, 150),
      });
    }
    if (rows.length === 0) continue;

    const candidate = {
      paperId: paper.id,
      paperTitle: titleOf(paper, titles.get(paper.id) ?? "Untitled"),
      rows,
    };
    // Most fields wins; between equally complete records prefer the one with
    // the tersest values, which is the clearer thing to read on a landing page.
    if (
      !best ||
      rows.length > best.rows.length ||
      (rows.length === best.rows.length && valueWeight(candidate) < valueWeight(best))
    ) {
      best = candidate;
    }
  }

  return best && best.rows.length >= 3 ? best : null;
}

function valueWeight(demo: ExtractionDemo): number {
  return demo.rows.reduce((sum, row) => sum + row.value.length, 0);
}

/** Longest competing value that still reads as a value rather than as prose. */
const CONFLICT_VALUE_LIMIT = 36;

/**
 * A real disagreement kept visible, to show that conflicts are not resolved
 * silently. Only conflicts between short, genuinely different values are shown:
 * two paragraphs of prose, or the same string in two casings, illustrate
 * nothing. The tersest qualifying conflict wins so the example stays readable.
 */
export function pickConflict(papers: StoredPaper[], summaries: PaperSummary[]): ConflictExample | null {
  const titles = new Map(summaries.map((paper) => [paper.id, paper.title ?? "Untitled"]));
  let best: ConflictExample | null = null;
  let bestWeight = Infinity;

  for (const paper of papers) {
    for (const { path, field } of walkFields(paper.record)) {
      if (field.status !== "CONFLICT" || field.conflict_values.length < 2) continue;

      const values = field.conflict_values.map((value) => formatValue(value).replace(/\s+/g, " ").trim());
      if (values.some((value) => !value || value.length > CONFLICT_VALUE_LIMIT)) continue;
      const distinct = new Set(values.map((value) => value.toLowerCase()));
      if (distinct.size < 2) continue;

      const weight = Math.max(...values.map((value) => value.length));
      if (weight >= bestWeight) continue;
      bestWeight = weight;
      best = {
        paperId: paper.id,
        paperTitle: titleOf(paper, titles.get(paper.id) ?? "Untitled"),
        label: path.split(".").at(-1)?.replaceAll("_", " ") ?? path,
        values,
      };
    }
  }
  return best;
}

const UNAVAILABLE: LandingData = {
  status: "unavailable",
  partial: null,
  totals: {
    papers: 0,
    domains: 0,
    papersWithFields: 0,
    extractedFields: 0,
    recordFields: 0,
    sourcedValues: 0,
    humanAudited: 0,
  },
  statuses: [],
  years: [],
  limitations: [],
  sections: [],
  families: [],
  datasets: [],
  extraction: null,
  conflict: null,
};

export async function loadLandingData(): Promise<LandingData> {
  let page: Awaited<ReturnType<typeof listPaperPage>>;
  let domains: Domain[];
  try {
    [page, domains] = await Promise.all([listPaperPage(), listDomains()]);
  } catch {
    return UNAVAILABLE;
  }

  const summaries = page.papers;
  const analyzed = summaries.filter(isAnalyzed);
  const settled = await Promise.all(analyzed.map((paper) => getPaper(paper.id).catch(() => null)));
  const records = settled.filter((paper): paper is StoredPaper => paper !== null);
  const missingRecords = settled.length - records.length;

  // The list endpoint is capped; say so rather than describing a subset as
  // "the corpus".
  const truncatedAt = page.total > summaries.length ? PAPER_PAGE_LIMIT : null;

  return {
    status: summaries.length === 0 ? "empty" : "ready",
    partial: missingRecords > 0 || truncatedAt !== null ? { missingRecords, truncatedAt } : null,
    totals: {
      papers: page.total,
      domains: domains.length,
      papersWithFields: analyzed.length,
      extractedFields: summaries.reduce((sum, paper) => sum + paper.extracted_field_count, 0),
      ...tallyEvidence(records),
    },
    statuses: tallyStatuses(records),
    years: tallyYears(summaries),
    limitations: tallyLimitations(records, summaries),
    sections: tallySections(records),
    families: tallyFamilies(records),
    datasets: tallyDatasets(records),
    extraction: pickExtractionDemo(records, summaries),
    conflict: pickConflict(records, summaries),
  };
}
